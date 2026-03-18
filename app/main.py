
from interfaz.app_shell import AppShell
from config import APP_TITLE, WINDOW_GEOM


if __name__ == "__main__":
    # IMPORTANT:
    # We disable auto-connect here to avoid "connection_refused" issues when
    # multiple UI pages (or other tools) try to connect to the drone.
    #
    # Use the "Conectar" buttons inside pages (Sensores / ROS2 Bridge) instead.
    app = AppShell(APP_TITLE, WINDOW_GEOM, connect_drone=False)
    app.mainloop()
