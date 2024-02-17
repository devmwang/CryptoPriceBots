import json


class AlertHandler:
    def __init__(self, client):
        self.client = client

    def set_alert(self, curr_price, alert_price):
        # Check if alert_price is bigger, equal to, or smaller than curr_price
        if alert_price > curr_price:
            price_movement = 'up'
        elif alert_price < curr_price:
            price_movement = 'down'
        else:
            price_movement = 'same'

        # Only set alert if price_movement exists
        if price_movement != 'same':
            # Open JSON file with persistent alert prices
            with open('cpb_store.json') as json_file:
                data = json.load(json_file)

                # Assign alert to proper JSON location
                if self.client.asset.upper() not in data["price-alerts"]:
                    data["price-alerts"][self.client.asset.upper()] = {'up': None, 'down': None}

                if price_movement == 'up':
                    data["price-alerts"][self.client.asset.upper()]['up'] = alert_price
                elif price_movement == 'down':
                    data["price-alerts"][self.client.asset.upper()]['down'] = alert_price

                # Dump in-memory JSON to persistent JSON file
                with open('cpb_store.json', 'w') as outfile:
                    json.dump(data, outfile, indent=4)

        # Set client variable alert price
        if price_movement == 'up':
            self.client.alert_up = alert_price
            return f"Set alert for {self.client.asset.upper()} above ${alert_price}."
        elif price_movement == 'down':
            self.client.alert_down = alert_price
            return f"Set alert for {self.client.asset.upper()} below ${alert_price}."

    def clear_alert(self, direction):
        # Open JSON file with persistent alert prices
        with open('cpb_store.json') as json_file:
            data = json.load(json_file)

            if self.client.asset.upper() in data["price-alerts"]:
                if direction == 'up':
                    data["price-alerts"][self.client.asset.upper()]['up'] = None
                elif direction == 'down':
                    data["price-alerts"][self.client.asset.upper()]['down'] = None

            # Dump in-memory JSON to persistent JSON file
            with open('cpb_store.json', 'w') as outfile:
                json.dump(data, outfile, indent=4)

        # Clear client var alert prices
        if direction == 'up':
            self.client.alert_up = None
        elif direction == 'down':
            self.client.alert_down = None

    def clear_all_alerts(self):
        # Open JSON file with persistent alert prices
        with open('cpb_store.json') as json_file:
            data = json.load(json_file)

            if self.client.asset.upper() in data["price-alerts"]:
                data["price-alerts"][self.client.asset.upper()]['up'] = None
                data["price-alerts"][self.client.asset.upper()]['down'] = None

            # Dump in-memory JSON to persistent JSON file
            with open('cpb_store.json', 'w') as outfile:
                json.dump(data, outfile, indent=4)

        # Clear client var alert prices
        self.client.alert_up = None
        self.client.alert_down = None
