import os
import json

"""
Class that reads a local json file which would store our local settings.
Check PlexServerDefaultConfigExample.json for an example.
"""
class CustomPlexConfig:
    def __init__(self, path):
        self.data = self._parse(path)

    def get(self, key, default=None):
        """ Returns the specified configuration value or <default> if not found.

            Parameters:
                key (str): Configuration variable to load.
                default: Default value to use if key not found.
        """
        if key in self.data:
            return self.data[key]
        else:
            return default
    
    def _parse(self, path):
        if os.path.isfile(path):
        # Load configuration file
            with open(path) as json_file:
                data = json.load(json_file)
            return data
        else:
            return {}
        

def main():
    default_config = CustomPlexConfig("PlexServerDefaultConfig.json")
    print(default_config.data)
        
if __name__ == '__main__':
    main()