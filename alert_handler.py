import json

class AlertHandler():
    def __init__(self, client):
        self.client = client


    def set_alert(self, index, curr_price, alert_price):
        # Check if alert_price is bigger, equal to, or smaller than curr_price
        if alert_price > curr_price:
            price_movement = 'up'
        elif alert_price < curr_price:
            price_movement = 'down'
        else:
            price_movement = 'same'

        # Only set alert if price_movement exists
        if (price_movement != 'same'):
            # Open JSON file with persistent alert prices
            with open('price_alerts.json') as json_file:
                data = json.load(json_file)

                # Assign alert to proper JSON location
                if price_movement == 'up':
                    data[self.client.pairs[index].upper()]['up'] = alert_price
                elif price_movement == 'down':
                    data[self.client.pairs[index].upper()]['down'] = alert_price

                # Dump in-memory JSON to persistent JSON file
                with open('price_alerts.json', 'w') as outfile:
                        json.dump(data, outfile, indent=4)

        # Set client variable alert price
        if (index == 0 or index == 1):
            if price_movement == 'up':
                self.client.alert_up[index] = alert_price
                return (f"Set alert for {self.client.pairs[index].upper()} above ${alert_price}.")
            elif price_movement == 'down':
                self.client.alert_down[index] = alert_price
                return (f"Set alert for {self.client.pairs[index].upper()} below ${alert_price}.")
        else:
            return ("BA DING")


    def clear_alert(self, index, up_or_down):
        # Open JSON file with persistent alert prices
        with open('price_alerts.json') as json_file:
            data = json.load(json_file)

            if (up_or_down == 'up'):
                data[self.client.pairs[index].upper()]['up'] = None
            elif (up_or_down == 'down'):
                data[self.client.pairs[index].upper()]['down'] = None
        
            # Dump in-memory JSON to persistent JSON file
            with open('price_alerts.json', 'w') as outfile:
                    json.dump(data, outfile, indent=4)

        # Clear client var alert prices
        if (up_or_down == 'up'):
            self.client.alert_up[index] = None
        elif (up_or_down == 'down'):
            self.client.alert_down[index] = None


    def clear_all_alerts(self):
        # Open JSON file with persistent alert prices
        with open('price_alerts.json') as json_file:
            data = json.load(json_file)

            data[self.client.pairs[0].upper()]['up'] = None
            data[self.client.pairs[0].upper()]['down'] = None
            data[self.client.pairs[1].upper()]['up'] = None
            data[self.client.pairs[1].upper()]['down'] = None

            # Dump in-memory JSON to persistent JSON file
            with open('price_alerts.json', 'w') as outfile:
                json.dump(data, outfile, indent=4)

        # Clear client var alert prices
        self.client.alert_up[0] = None
        self.client.alert_down[0] = None
        self.client.alert_up[1] = None
        self.client.alert_down[1] = None
