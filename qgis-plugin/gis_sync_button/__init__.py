def classFactory(iface):
    from .plugin import GisSyncButtonPlugin
    return GisSyncButtonPlugin(iface)
