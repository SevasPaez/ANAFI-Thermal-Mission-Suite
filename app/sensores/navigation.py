
import math

def enu_from_llh(lat, lon, alt, lat0, lon0, alt0):
    lat0_rad = math.radians(lat0)
    m_per_deg_lat = 111_320.0
    m_per_deg_lon = 111_320.0 * math.cos(lat0_rad)
    dE = (lon - lon0) * m_per_deg_lon
    dN = (lat - lat0) * m_per_deg_lat
    dU = (alt - alt0)
    return (dE, dN, dU)

def body_vel_to_world(vx, vy, vz, yaw):
    cy, sy = math.cos(yaw), math.sin(yaw)
    vE =  vy * cy + vx * sy
    vN = -vy * sy + vx * cy
    vU = -vz
    return (vE, vN, vU)
