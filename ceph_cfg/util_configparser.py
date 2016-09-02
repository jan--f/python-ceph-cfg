try:
    import ConfigParser
except:
    import configparser as ConfigParser


class ConfigParserCeph(ConfigParser.ConfigParser):

    def optionxform(self, s):
        """
        Make config files with white space use '_'
        """
        stripped = s.strip()
        replaced = stripped.replace(' ', '_')
        return replaced

