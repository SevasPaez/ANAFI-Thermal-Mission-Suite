
class CameraController:
    def __init__(self, drone_client):
        self.drone_client = drone_client
        self.running = False
    def start_rgb(self): self.running=True
    def start_thermal(self): self.running=True
    def stop(self): self.running=False
