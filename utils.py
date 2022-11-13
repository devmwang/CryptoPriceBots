class Utils:
    def __init__(self, client):
        self.client = client

    def get_activity_label(self):
        return f"CA${round((self.client.usd_price * self.client.usd_cad_conversion), 4)}"
