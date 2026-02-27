import json
from datetime import datetime
from uuid import uuid4, UUID
from typing import Dict, List, Optional

from app.domain.models import (
    Match, Team, Player, DomainEvent, GameClock, 
    MatchID, TeamID, PlayerID, CourtLocation
)

class IndalwebAdapter:
    """
    Anti-Corruption Layer (ACL).
    Convierte el JSON propietario de la Federación (Indalweb/Gesdeportiva)
    en nuestro Modelo de Dominio limpio.
    """

    def __init__(self):
        # Cache local para no duplicar entidades durante el parseo
        self._teams: Dict[str, Team] = {} # Key: External ID string
        self._players: Dict[str, Player] = {} # Key: External ID string

    def decode_hex_string(self, hex_str: str) -> str:
        """
        Decodifica los strings ofuscados de Indalweb.
        Ej: "41004200" -> "AB" (UTF-16 Little Endian encoded as Hex)
        """
        try:
            if not hex_str: return ""
            # Convertimos hex a bytes y decodificamos utf-16-le
            return bytes.fromhex(hex_str).decode('utf-16-le')
        except Exception:
            # Si falla, devolvemos el original (por si acaso no era hex)
            return hex_str

    def parse_time(self, time_str: str, period: int) -> GameClock:
        """Convierte '00:08:23.5' a GameClock"""
        try:
            # Formato esperado: HH:MM:SS.f o MM:SS
            parts = time_str.split(':')
            if len(parts) == 3:
                h, m, s = parts
                minutes = int(m) + (int(h) * 60)
                seconds = float(s)
            else:
                minutes = 0
                seconds = 0.0
            
            return GameClock(
                period=period,
                minutes=minutes,
                seconds=seconds,
                total_seconds_remaining=(minutes * 60) + seconds
            )
        except:
            return GameClock(period=period, minutes=0, seconds=0, total_seconds_remaining=0)

    def load_match(self, raw_json: dict) -> Match:
        """Método principal: JSON -> Domain Match"""
        
        data_partido = raw_json.get("partido", {})
        data_envivo = raw_json.get("envivo", {})
        
        # 1. Crear Equipos
        # Indalweb nos da ID numérico simple (idlocal) y el Hash largo (idclublocal)
        # Usaremos el numérico como referencia externa principal por ser más legible
        local_ext_id = str(data_partido.get("idlocal"))
        visitor_ext_id = str(data_partido.get("idvisitante"))
        
        home_team = Team(
            id=TeamID(uuid4()),
            name=data_partido.get("local", "Unknown Local"),
            external_refs={"indalweb_id": local_ext_id, "indalweb_hash": data_partido.get("idclublocal")}
        )
        self._teams[local_ext_id] = home_team

        away_team = Team(
            id=TeamID(uuid4()),
            name=data_partido.get("visitante", "Unknown Visitor"),
            external_refs={"indalweb_id": visitor_ext_id, "indalweb_hash": data_partido.get("idclubvisitante")}
        )
        self._teams[visitor_ext_id] = away_team

        # 2. Parsear Jugadores (Local y Visitante)
        self._parse_players(data_envivo.get("jugadoresenpistalocal", []), home_team)
        self._parse_players(data_envivo.get("jugadoresenpistavisitante", []), away_team)

        # 3. Crear el objeto Match (Sin eventos aun)
        match = Match(
            id=MatchID(uuid4()),
            date=datetime.now(), # TODO: Parsear fecha real del JSON si viene ('fechaultimaactualizacion' es un timestamp .NET)
            home_team=home_team,
            away_team=away_team,
            home_score=data_partido.get("tanteo_local", 0),
            away_score=data_partido.get("tanteo_visitante", 0)
        )

        # 4. Parsear Eventos (Historial de acciones)
        raw_events = data_envivo.get("historialacciones", [])
        # Invertimos la lista porque suele venir del más reciente al más antiguo
        for raw_event in reversed(raw_events):
            domain_event = self._parse_single_event(raw_event, match.id)
            if domain_event:
                match.add_event(domain_event)

        return match

    def _parse_players(self, players_list: list, team: Team):
        for p_data in players_list:
            # El ID del jugador viene cifrado en el campo "id"
            raw_id_hex = p_data.get("id", "")
            # A veces el nombre también viene codificado o sucio, aquí asumimos que "nombre" es legible
            # si quisieras decodificar el ID real (DNI o licencia), habría que ver si el hex decode funciona
            
            player = Player(
                id=PlayerID(uuid4()),
                name=p_data.get("nombre", "Unknown"),
                number=str(p_data.get("dorsal", "0")),
                external_refs={"indalweb_hex": raw_id_hex}
            )
            # Guardamos en diccionario para búsqueda rápida por dorsal+equipo luego
            # Nota: Usamos una clave compuesta temporal o el hex si es único
            self._players[raw_id_hex] = player

    def _parse_single_event(self, raw: dict, match_id: UUID) -> Optional[DomainEvent]:
        # Filtramos eventos "basura"
        if raw.get("accion_tipo") in ["FINAL-PERIODO", "FINAL-PARTIDO"]:
            # Podríamos guardarlos para marcar cuartos, pero por ahora simplificamos
            return None

        # Identificar equipo (el JSON trae 'equipo_id' numérico)
        team_ext_id = str(raw.get("equipo_id"))
        team_obj = self._teams.get(team_ext_id)
        
        # Identificar jugador
        # El historial a veces NO trae el ID largo del jugador, solo el dorsal.
        # Esto es un problema común. Necesitamos buscar en self._players quien tiene ese dorsal en ese equipo.
        # Por simplicidad ahora, lo dejamos como None si no hay ID directo, 
        # pero en producción haríamos un lookup: (team_id, dorsal) -> Player
        player_obj = None 
        # TODO: Implementar búsqueda de jugador por dorsal + equipo

        # Parsear tiempo
        clock = self.parse_time(raw.get("tiempo_partido", "00:00:00"), raw.get("numero_periodo", 1))

        # Coordenadas (Si vienen a 0, ponemos None)
        x = float(raw.get("posicion_x", 0))
        y = float(raw.get("posicion_y", 0))
        loc = CourtLocation(x=x, y=y) if (x > 0 or y > 0) else None

        return DomainEvent(
            match_id=MatchID(match_id),
            team_id=TeamID(team_obj.id) if team_obj else None,
            player_id=PlayerID(player_obj.id) if player_obj else None,
            clock=clock,
            location=loc,
            event_type=raw.get("accion_tipo"),
            metadata={
                "raw_id": raw.get("autoincremental_id"),
                "info": raw.get("informacion_adicional")
            }
        )