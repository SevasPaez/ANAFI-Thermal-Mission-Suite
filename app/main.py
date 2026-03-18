
from interfaz.app_shell import AppShell
from config import APP_TITLE, WINDOW_GEOM

if __name__ == "__main__":

    app = AppShell(APP_TITLE, WINDOW_GEOM, connect_drone=False)
    app.mainloop()
