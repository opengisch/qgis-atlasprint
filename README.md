## AtlasPrint: QGIS Server Plugin to export PDF from composer with atlas capabilities

### Description

This plugin adds a new request to QGIS 3 Server `getprintatlas` which allows to export a print composer with an atlas configured, but passing an expression parameter to choose which feature is the current atlas feature.

### Installation

We assume you have a fully functional QGIS Server with Xvfb. See [the QGIS3 documentation](https://docs.qgis.org/3.4/en/docs/user_manual/working_with_ogc/server/index.html).

We need to download the plugin, and tell QGIS Server where the plugins are stored, then reload the web server.
For example on Debian:

```bash
# Create needed directory to store plugins
mkdir -p /srv/qgis/plugins

# Get last version
cd /srv/qgis/plugins
wget "https://github.com/3liz/qgis-atlasprint/archive/master.zip"
unzip master.zip
mv qgis-atlasprint-master atlasprint

# Make sure correct environment variables are set in your web server configuration
# for example in Apache2 with mod_fcgid
nano /etc/apache2/mods-available/fcgid.conf
FcgidInitialEnv QGIS_PLUGINPATH "/srv/qgis/plugins/"

# Reload server, for example with Apache2
service apache2 reload
```

You can now test your installation.

### API

The layout must have an atlas enabled.

This plugin adds some new requests to the WMS service:
* `REQUEST=GETCAPABILITIESATLAS`: Return the plugin version
* `REQUEST=GETPRINTATLAS`
  * `TEMPLATE`: **required**, name of the layout to use.
  * `EXP_FILTER`: **required**, it must be HTML escaped.
    * For example, to request `fid=12`, it must be `&EXP_FILTER=fid%3D12`.
    * An expression returning many features can also be used, for instance `&EXP_FILTER=id in ('1','2')` will return a PDF with 2 pages.
  * `SCALE`: *optional*. If not provided, the default configuration in the atlas is used.
    * If set to an integer number, the scale will be fixed. Exclusive with `SCALES`.
  * `SCALES`: *optional*. If not provided, the default configuration in the atlas is used.
    * Comma separated list of values. If set, these predefined scales are used. Exclusive with `SCALE`.
    * For instance `SCALES=400,1000`.

The only config that the plugin will not follow is the file pattern defined in QGIS Desktop, if it outputs many PDF.
``