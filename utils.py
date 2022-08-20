

class Utils():
    def __init__(self, client):
        self.client = client
    
    def get_activity_label(self):
        if self.client.dual:
            return f"{self.client.pairs[1]} - ${round(self.client.usd_price[1], 4)}"
        else:
            return f"CA${round((self.client.usd_price[0] * self.client.usd_cad_conversion), 4)}"