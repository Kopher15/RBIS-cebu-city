import sys
from pathlib import Path
from qgis.PyQt.QtWidgets import QAction
from qgis.core import QgsMessageLog, Qgis


class GisSyncButtonPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.action = None
        self.tb = None

    def initGui(self):
        try:
            profile_py = str(Path(__file__).parent.parent.parent)
            if profile_py not in sys.path:
                sys.path.insert(0, profile_py)

            import gis_sync_action

            self.tb = self.iface.addToolBar("GIS Sync")
            self.tb.setObjectName("GISSyncToolBar")

            icon = self.iface.mainWindow().style().standardIcon(35)
            self.action = QAction(icon, "Sync + Publish Dashboard", self.iface.mainWindow())
            self.action.setToolTip(
                "Sync GeoPackage → PostGIS, then export GeoJSON and push to GitHub/Vercel"
            )
            self.action.triggered.connect(gis_sync_action.run_sync)
            self.tb.addAction(self.action)

            QgsMessageLog.logMessage("GIS Sync toolbar installed (plugin)", "gis_sync", Qgis.Info)
        except Exception as e:
            QgsMessageLog.logMessage(f"Plugin install failed: {e}", "gis_sync", Qgis.Critical)

    def unload(self):
        if self.action and self.tb:
            self.tb.removeAction(self.action)
        if self.tb:
            self.tb.deleteLater()
        self.action = None
        self.tb = None
