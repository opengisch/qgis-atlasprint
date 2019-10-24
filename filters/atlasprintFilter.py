"""
***************************************************************************
    QGIS Server Plugin Filters: Add a new request to print a specific atlas
    feature
    ---------------------
    Date                 : October 2017
    Copyright            : (C) 2017 by Michaël Douchin - 3Liz
    Email                : mdouchin at 3liz dot com
***************************************************************************
*                                                                         *
*   This program is free software; you can redistribute it and/or modify  *
*   it under the terms of the GNU General Public License as published by  *
*   the Free Software Foundation; either version 2 of the License, or     *
*   (at your option) any later version.                                   *
*                                                                         *
***************************************************************************
"""

import re
import json
import os
import tempfile

from uuid import uuid4
from pathlib import Path
from configparser import ConfigParser
from xml.etree import ElementTree as ET

from qgis.server import QgsServerFilter
from qgis.gui import QgsMapCanvas, QgsLayerTreeMapCanvasBridge
from qgis.core import Qgis, QgsProject, QgsMessageLog, QgsExpression
from qgis.core import QgsPrintLayout, QgsReadWriteContext, QgsLayoutItemMap, QgsLayoutExporter
from qgis.PyQt.QtCore import QByteArray
from qgis.PyQt.QtXml import QDomDocument


class AtlasPrintFilter(QgsServerFilter):

    def __init__(self, server_iface):
        QgsMessageLog.logMessage('atlasprintFilter.init', 'atlasprint', Qgis.Info)
        super(AtlasPrintFilter, self).__init__(server_iface)

        self.server_iface = server_iface
        self.handler = None
        self.predefined_scales = [
            500, 1000, 2500, 5000, 10000, 25000, 50000, 100000, 250000, 500000, 1000000,
            2500000, 5000000, 10000000, 25000000, 50000000, 100000000, 250000000
        ]

        self.metadata = {}
        self.get_plugin_metadata()

        # QgsMessageLog.logMessage("atlasprintFilter end init", 'atlasprint', Qgis.Info)

    def get_plugin_metadata(self):
        """
        Get plugin metadata.
        """
        metadata_file = Path(__file__).resolve().parent.parent / 'metadata.txt'
        if metadata_file.is_file():
            config = ConfigParser()
            config.read(str(metadata_file))
            self.metadata['name'] = config.get('general', 'name')
            self.metadata['version'] = config.get('general', 'version')

    def set_json_response(self, status, body):
        """
        Set response with given parameters.
        """
        self.handler.clear()
        self.handler.setResponseHeader('Content-type', 'text/json')
        self.handler.setResponseHeader('Status', status)
        self.handler.appendBody(json.dumps(body).encode('utf-8'))

    # noinspection PyPep8Naming
    def responseComplete(self):
        """
        Send new response.
        """
        self.handler = self.server_iface.requestHandler()
        params = self.handler.parameterMap()

        # Check if needed params are passed
        # If not, do not change QGIS Server response
        service = params.get('SERVICE')
        if not service:
            return

        if service.lower() != 'wms':
            return

        # Check if getprintatlas request. If not, just send the response
        if 'REQUEST' not in params or params['REQUEST'].lower() not in ['getprintatlas', 'getcapabilitiesatlas']:
            return

        # Get capabilities
        if params['REQUEST'].lower() == 'getcapabilitiesatlas':
            body = {
                'status': 'success',
                'metadata': self.metadata
            }
            self.set_json_response('200', body)
            return

        # Check if needed params are set
        required = ['TEMPLATE', 'EXP_FILTER']
        if not all(elem in params for elem in required):
            body = {
                'status': 'fail',
                'message': 'Missing parameters: {} are required.'.format(' '.join(required))
            }
            self.set_json_response('400', body)
            return

        feature_filter = params['EXP_FILTER']

        # check expression
        expression = QgsExpression(feature_filter)
        if expression.hasParserError():
            body = {
                'status': 'fail',
                'message': 'An error occurred while parsing the given expression: {}'.format(expression.parserErrorString())
                }
            QgsMessageLog.logMessage('ERROR EXPRESSION: {}'.format(expression.parserErrorString()), 'atlasprint', Qgis.Critical)
            self.set_json_response('400', body)
            return

        # noinspection PyBroadException
        try:
            pdf = self.print_atlas(
                project_path=self.serverInterface().configFilePath(),
                layout_name=params['TEMPLATE'],
                predefined_scales=self.predefined_scales,
                feature_filter=feature_filter
            )
        except Exception as e:
            pdf = None
            QgsMessageLog.logMessage('PDF CREATION ERROR: {}'.format(e), 'atlasprint', Qgis.Critical)

        if not pdf:
            body = {
                'status': 'fail',
                'message': 'ATLAS - Error while generating the PDF'
            }
            QgsMessageLog.logMessage('No PDF generated in {}'.format(pdf), 'atlasprint', Qgis.Critical)
            self.set_json_response('500', body)
            return

        # Send PDF
        self.handler.clear()
        self.handler.setResponseHeader('Content-type', 'application/pdf')
        self.handler.setResponseHeader('Status', '200')

        # noinspection PyBroadException
        try:
            with open(pdf, 'rb') as f:
                loads = f.readlines()
                ba = QByteArray(b''.join(loads))
                self.handler.appendBody(ba)
        except Exception as e:
            QgsMessageLog.logMessage('PDF READING ERROR: {}'.format(e), 'atlasprint', Qgis.Critical)
            body = {
                'status': 'fail',
                'message': 'Error occurred while reading PDF file',
            }
            self.set_json_response('500', body)
        finally:
            os.remove(pdf)

        return

    @staticmethod
    def print_atlas(project_path, layout_name, predefined_scales, feature_filter):
        """Generate an atlas.

        :param project_path: Path to project to render as atlas.
        :type project_path: basestring

        :param layout_name: Name of the layout
        :type layout_name: basestring

        :param predefined_scales: List of scales which are available to render the feature.
        :type predefined_scales: list

        :param feature_filter: QGIS Expression to use to select the feature.
        It can return many features, a multiple pages PDF will be returned.
        :type feature_filter: basestring

        :return: Path to the PDF.
        :rtype: basestring
        """
        # Get composer from project
        # in QGIS 2, we can't get composers without iface
        # so we reading project xml and extract composer
        # TODO Since QGIS 3.0, we should be able to use project layoutManager()
        # noinspection PyPep8Naming

        composer_xml = None
        with open(project_path, 'r') as f:
            tree = ET.parse(f)
            for elem in tree.findall('.//Composer[@title="{}"]'.format(layout_name)):
                composer_xml = ET.tostring(
                    elem,
                    encoding='utf8',
                    method='xml'
                )
            if not composer_xml:
                for elem in tree.findall('.//Layout[@name="{}"]'.format(layout_name)):
                    composer_xml = ET.tostring(
                        elem,
                        encoding='utf8',
                        method='xml'
                    )

        if not composer_xml:
            QgsMessageLog.logMessage('Layout XML not parsed !', 'atlasprint', Qgis.Critical)
            return

        document = QDomDocument()
        document.setContent(composer_xml)

        # Get canvas, map setting & instantiate composition
        canvas = QgsMapCanvas()
        project = QgsProject()
        project.read(project_path)
        bridge = QgsLayerTreeMapCanvasBridge(
            project.layerTreeRoot(),
            canvas
        )
        bridge.setCanvasLayers()

        layout = QgsPrintLayout(project)

        # Load content from XML
        layout.loadFromTemplate(
            document,
            QgsReadWriteContext(),
        )

        atlas = layout.atlas()
        atlas.setEnabled(True)

        atlas_map = layout.referenceMap()
        atlas_map.setAtlasDriven(True)
        atlas_map.setAtlasScalingMode(QgsLayoutItemMap.Predefined)

        layout.reportContext().setPredefinedScales(predefined_scales)

        # Filter feature here to avoid QGIS looping through every feature when doing
        # composition.setAtlasMode(QgsComposition.ExportAtlas)

        coverage_layer = atlas.coverageLayer()

        # Filter by FID as QGIS cannot compile expressions with $id or other $ vars
        # which leads to bad performance for big dataset
        use_fid = None
        if '$id' in feature_filter:
            ids = list(map(int, re.findall(r'\d+', feature_filter)))
            if len(ids) > 0:
                use_fid = ids[0]
        # if use_fid:
        #     qReq = QgsFeatureRequest().setFilterFid(use_fid)
        # else:
        #     qReq = QgsFeatureRequest().setFilterExpression(feature_filter)

        # Change feature_filter in order to improve performance
        pks = coverage_layer.dataProvider().pkAttributeIndexes()
        if use_fid and len(pks) == 1:
            pk = coverage_layer.dataProvider().fields()[pks[0]].name()
            feature_filter = '"{}" IN ({})'.format(pk, use_fid)
            QgsMessageLog.logMessage('feature_filter changed into: {}'.format(feature_filter), 'atlasprint', Qgis.Info)
            # qReq = QgsFeatureRequest().setFilterExpression(feature_filter)
        atlas.setFilterFeatures(True)
        atlas.setFilterExpression(feature_filter)

        # setup settings
        settings = QgsLayoutExporter.PdfExportSettings()
        export_path = os.path.join(
            tempfile.gettempdir(),
            '{}_{}.pdf'.format(layout_name, uuid4())
        )
        exporter = QgsLayoutExporter(layout)
        result = exporter.exportToPdf(atlas, export_path, settings)

        if result[0] != QgsLayoutExporter.Success:
            QgsMessageLog.logMessage('export not generated {}'.format(export_path), 'atlasprint', Qgis.Critical)
            return

        if not os.path.isfile(export_path):
            QgsMessageLog.logMessage('export not generated {}'.format(export_path), 'atlasprint', Qgis.Critical)
            return

        # Do not use Qgis.Success, it becomes a critical
        QgsMessageLog.logMessage('successful export in generated {}'.format(export_path), 'atlasprint', Qgis.Info)
        return export_path
