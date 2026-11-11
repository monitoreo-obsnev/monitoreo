"""Help of the options of the MonitorEO panel, shown by their buttons ⓘ: short texts in English (rich text of Qt),
each ending with a link to the section of the manual (the English pages of the wiki of the repository) that explains
it. The help of the variable and of the pixel filters also describes the variable chosen (variable_help,
filters_help), with the references of its formula and of its data (monitoreo.references), with their DOIs; that of
the data of Earth Engine given by their ID, what services.describe_asset read of them (data_help, data_summary)."""

from . import deps

deps.setup_path()
from monitoreo import about, references, sensors, services  # noqa: E402

MANUAL = f'{about.MANUAL}/QGIS-plugin'  # the English page of the plugin in the wiki
FILTER_NAMES = {'clouds': 'clouds', 'water': 'water', 'snow': 'snow', 'aerosols': 'aerosols'}
MEASURED = {'water': 'water', 'snow': 'snow', 'aerosols': 'aerosols'}


def esc(text):
	"""TEXT for the rich text of Qt."""
	return str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def cite_html(refs, credits=(), title='References'):
	"""The references REFS (dictionaries of monitoreo.references) and the credits of the data as rich text, with the
	links of their DOIs."""
	if not refs:
		return ''
	link = lambda url: f' <a href="{esc(url)}">{esc(url)}</a>' if url else ''
	items = ''.join(f"<li>{esc(r['citation'])}{link(r.get('url'))}</li>" for r in refs)
	return f'<p><b>{title}</b></p><ul>{items}</ul>' + (f"<p>{esc(' · '.join(credits))}</p>" if credits else '')


def method_references(name):
	"""The references of a method of the catalog (trends, burn_severity, rbr)."""
	from monitoreo import catalog
	return [references.get(i) for i in catalog.load()['methods'].get(name, [])]


def manual(page):
	"""Link to PAGE of the wiki (an English page, with the anchor of its section: 'Concepts#regions')."""
	return f'<p><a href="{about.MANUAL}/{page}">More in the manual</a></p>'


HELP = {
	'project':
		'<p><b>Empty</b>: the computations run in Earth Engine with the <b>shared account of MonitorEO</b>, with no '
		'sign-in and no Earth Engine account of your own. With it you cannot export to Google Drive: the GeoTIFFs are '
		'downloaded to this computer.</p>'
		'<p>With <b>your Google Cloud project</b> registered in Earth Engine, the computations run with your Google '
		'account and count in the quota of that project; then you can also export to your Google Drive. It is '
		'remembered for the next time.</p>'
		'<p><b>Authenticate…</b> opens the browser to sign in with your Google account, once on each computer (as '
		'<code>earthengine authenticate</code>); it is only needed to use your project. <b>Connect</b> checks that '
		'the connection works; it is not required, because each computation connects by itself.</p>'
		+ manual('Getting-started'),
	'eecu':
		'<p>The bar shows what part of your EECUs (the compute units of Earth Engine) of this month you have spent. '
		'They restart on the 1st of each month.</p>'
		'<p>With the <b>shared account</b> (empty project) they are your <b>research EECUs</b>: each user has their '
		'own (25 EECU-hours a month, while the project of MonitorEO has EECUs left for its users), so that no one '
		'spends those of everyone, and they are <b>only for research</b>. '
		'When you have spent them, the shared account does not compute for you until the next month: switch to your '
		'own account by writing your project in <b>Project</b> and pressing <b>Authenticate…</b>.</p>'
		'<p>With <b>your project</b>, they are those of that project, against the monthly quota of its Earth Engine '
		'<b>tier</b>, chosen in the list (Community: 150 EECU-hours a month; Contributor: 1,000; Partner: 100,000). To '
		'read them, the project must have the Cloud Monitoring API enabled (free). When the quota is spent, Earth '
		'Engine does not stop, but it computes much more slowly until the next month.</p>'
		'<p>It warns when less than 10% is left. The bar is updated after each computation; <b>Check</b> asks '
		'again.</p>'
		+ manual('Concepts#eecus-spent-this-month'),
	'region':
		'<p>What is computed over:</p><ul>'
		'<li><b>Layer</b>: the polygons of a layer of the project, the selected ones or, if there is no selection, all '
		'of them. Each polygon gives its own series.</li>'
		'<li><b>Map extent</b>: the rectangle seen in the map when the button of the computation is pressed.</li>'
		'<li><b>Protected area (WDPA)</b>: an area of the World Database on Protected Areas, searched by its '
		'name.</li>'
		'<li><b>Administrative unit (FAO GAUL)</b>: a region, province or municipality (levels 1 and 2 of FAO GAUL '
		'2025), searched by its name.</li>'
		'<li><b>Country</b>: a whole country, by its ISO3 code (FAO GAUL 2025). Big: use MODIS or a coarse pixel.</li>'
		'<li><b>Ecoregion at the center of the map</b>: the RESOLVE 2017 ecoregion that contains the center of the '
		'view.</li>'
		'<li><b>Island at the center of the map</b>: the island of more than 1 km² (Global Islands, Sayre et al. '
		'2019) that contains the center of the view.</li></ul>' + manual('Concepts#regions'),
	'layer':
		'<p>Layer of polygons of the project, in any coordinate system. If it has selected features, only those are '
		'used; if not, all of them. Each polygon gives its own series (a line in the chart).</p>'
		'<p>Layers with more than 20,000 vertices are simplified before they are sent to Earth Engine.</p>'
		+ manual('Concepts#regions'),
	'name_field':
		'<p>Field with the name of each polygon, which identifies its series in the chart, the table and the CSV. '
		'Empty: the number of the feature in QGIS.</p>' + manual('Concepts#regions'),
	'wdpa':
		'<p>Write part of the name of a protected area and press <b>Search</b> (or Enter): the list <b>Area</b> brings '
		'up to 30 areas of the <a href="https://www.protectedplanet.net">WDPA</a> with that text in their name. With '
		'<b>Ramsar only</b>, only the Ramsar sites (Wetlands of International Importance; those that the WDPA has only '
		'as points are not there).</p>'
		+ manual('QGIS-plugin#2-choose-the-region'),
	'admin':
		'<p>Write part of the name of an administrative unit, choose its level (1: regions, states, provinces...; 2: '
		'provinces, districts, municipalities...) and, if you like, its country (ISO3 code, e.g. ESP), and press '
		'<b>Search</b>: the list <b>Unit</b> brings up to 30 units of '
		'<a href="https://data.apps.fao.org">FAO GAUL 2025</a> with their full name.</p>'
		+ manual('QGIS-plugin#2-choose-the-region'),
	'country':
		'<p>The ISO3 code of a country (ESP, PRT, FRA...): the whole country, as the union of its regions of FAO GAUL '
		'2025. A country is big: compute with MODIS or with a coarse pixel.</p>' + manual('Concepts#regions'),
	'wdpa_area':
		'<p>The protected area over which it computes. Each entry tells its name, its designation, its country, its '
		'area and its WDPA ID.</p>'
		'<p>Look at the designation: the same name often has several designations (national park, natural park, SAC, '
		'SPA) with different boundaries.</p>' + manual('Concepts#regions'),
	'variable':
		'<p>Variable and sensor. Each entry tells the variable, the sensor, the pixel size and the Earth Engine '
		'collection. Sentinel-2 (10 m) starts in 2017; Landsat (30 m), in 1984, and MODIS (from 250 m to 4.6 km), in '
		'2000: for long series and trends, Landsat or MODIS.</p>',
	'period':
		'<p>First and last day, both included. Each sensor has its dates (see the help of <b>Variable</b>). If you '
		'check <b>Compare with</b>, this is the reference period.</p>'
		'<p>Long periods with Sentinel-2 over big areas take minutes: start with one year.</p>'
		+ manual('Concepts#period-and-season'),
	'compare':
		'<p>Check <b>other period</b> to compare it with the period above, the reference period:</p><ul>'
		'<li><b>Compute the time series</b> gives the mean of each part of the year (month, 16 days or year, '
		'according to the <b>Step</b>; not daily) in each period and their difference (other − reference).</li>'
		'<li><b>Add the layer to the map</b> adds the difference of the metric of the map, with the bands difference, '
		'reference and other.</li></ul>'
		'<p>The trends and the exports to Google Drive use only the reference period.</p>'
		+ manual('Concepts#comparison-of-two-periods'),
	'season':
		'<p>With the check box <b>only</b>, only the days between those two dates (MM-DD) of each year of the period '
		'count: from 06-01 to 09-30, the summer. It can cross the end of the year (from 11-01 to 02-28): then it '
		'counts in the year in which it starts.</p><p>It applies to everything: series, maps, trends, comparisons and '
		'exports.</p>'
		+ manual('Concepts#period-and-season'),
	'theme':
		'<p>First the theme, then its variables: <b>Vegetation</b> (NDVI, EVI, LAI), <b>Water</b> (NDWI, LSWI, '
		'chlorophyll), <b>Snow</b> (NDSI, snow cover frequency), <b>Fire</b> (NBR, and the burn severity of a fire), '
		'<b>Energy and temperature</b> '
		'(land surface temperature, albedo, evapotranspiration), <b>Atmosphere</b> (aerosols, cloud frequency), '
		'<b>Climate</b> (precipitation, temperature, water balance, WorldClim) and <b>Terrain</b> (elevation, slope). '
		'<b>All the variables</b> lists every one.</p>'
		'<p>A theme can have analyses of its own, shown only in it (and with <b>All the variables</b>): the '
		'<b>Burn severity of a fire</b>, in <b>Fire</b>.</p>'
		'<p>Two more themes compute data of Earth Engine outside the catalog of MonitorEO, instead of a variable: '
		'<b>Earth Engine data (by its ID)</b>, any image or collection of images of Earth Engine given by its ID, and '
		'<b>GEE Community Catalog</b>, the datasets of the '
		'<a href="https://gee-community-catalog.org">GEE Community Catalog</a> chosen by its themes. A collection of '
		'images with dates has maps, time series, trends and comparisons; a fixed image, only maps.</p>'
		+ manual('Concepts#variables'),
	'community_theme':
		'<p>The themes of the <a href="https://gee-community-catalog.org">GEE Community Catalog</a>: datasets shared by '
		'the community of Earth Engine as public assets (<code>projects/sat-io/open-datasets/...</code> and others), '
		'of population, elevation, soils, land cover, hydrology, vegetation, climate, fires... Each theme tells how '
		'many images and collections of images it has.</p>'
		'<p>MonitorEO keeps a copy of its index, so these lists need neither Earth Engine nor the internet. Its tables '
		'are not there: MonitorEO computes images.</p>'
		+ manual('QGIS-plugin#gee-community-catalog'),
	'community_dataset':
		'<p>The datasets of the theme by their title, each one an <i>image</i> or a <i>collection</i> of images (its '
		'tooltip gives its ID, provider and licence). Choosing one writes its ID in <b>Earth Engine ID</b> and reads it '
		'in Earth Engine (its bands).</p>'
		'<p>The index of the community catalog has no units, scale or offset of the bands: read them in the page of '
		'the dataset (the link under the options), which also says how to cite it, and write them in <b>Band '
		'scale</b>, <b>Band offset</b> and <b>Unit (UDUNITS)</b>.</p>'
		+ manual('Concepts#gee-community-catalog'),
	'asset':
		'<p>The ID of any image or collection of images of Earth Engine: the text between the quotes of '
		'<code>ee.Image(\'...\')</code> or <code>ee.ImageCollection(\'...\')</code> in the page of the dataset, e.g. '
		'<code>IDAHO_EPSCOR/TERRACLIMATE</code> (in the '
		'<a href="https://developers.google.com/earth-engine/datasets">Earth Engine data catalog</a>), '
		'<code>projects/sat-io/open-datasets/FABDEM</code> (in the GEE Community Catalog) or an asset of your project. '
		'Private assets need your own account (your project in <b>Project</b>), or to be shared with it.</p>'
		'<p><b>Read</b> reads in Earth Engine what it is (an image or a collection of images) and its bands and, for '
		'the Earth Engine data catalog, the units, scale and offset of each band, its licence and how to cite it. It '
		'reads metadata, without computing.</p>'
		'<p>It is computed like a variable over the region, with the period, the season, the metrics and the '
		'conditions of <b>Only the pixels where</b>, but without the pixel filters of MonitorEO (clouds, water, snow, '
		'aerosols) nor true colour: these data keep only their own mask. The results are named by the ID and the band, '
		'have the unit given and cite the dataset as its record says.</p>'
		+ manual('QGIS-plugin#earth-engine-data-by-its-id'),
	'asset_band':
		'<p>The band that is computed (one). <b>Read</b> lists them, with their description, unit and pixel size in '
		'their tooltips; you can also write it. Choosing one fills its <b>Band scale</b>, <b>Band offset</b> and '
		'<b>Unit (UDUNITS)</b> as its record says.</p>'
		'<p>Bands with classes or bit flags (land cover, quality) are codes, not quantities: their mean or median mean '
		'nothing; use the <b>Minimum</b> or the <b>Maximum</b>.</p>'
		+ manual('QGIS-plugin#earth-engine-data-by-its-id'),
	'asset_use':
		'<ul><li><b>Images with dates (collection)</b>: a collection of images over time (e.g. the monthly '
		'TerraClimate), aggregated in time like the variables of MonitorEO: maps of a period, time series, trends and '
		'comparisons of periods.</li>'
		'<li><b>Fixed image (image)</b>: an image without dates (e.g. WorldClim, a land cover map), or the mosaic of a '
		'collection of tiles (e.g. a DEM): like the elevation, only its map and its export; the period, the metrics, '
		'the time series and the trends do not apply.</li></ul>'
		'<p><b>Read</b> chooses what its record suggests; an image can only be a fixed image.</p>'
		+ manual('Concepts#earth-engine-data-by-its-id'),
	'band_scale':
		'<p>Many datasets store their values as integers with a factor: the value is the stored one times the '
		'<b>Band scale</b>, plus the <b>Band offset</b> (e.g. 0.0001 for the NDVI of MODIS, 0.1 for temperatures '
		'stored in tenths of a degree). Empty: 1, the values as stored.</p>'
		'<p><b>Read</b> fills it from the record of the Earth Engine data catalog; for other data, read it in the page '
		'of the dataset.</p>'
		+ manual('Concepts#earth-engine-data-by-its-id'),
	'band_offset':
		'<p>What is added to the values after the <b>Band scale</b> (e.g. -273.15 to turn kelvin into degrees Celsius, '
		'with the unit <code>degC</code>). Empty: 0.</p>'
		'<p><b>Read</b> fills it from the record of the Earth Engine data catalog, if it has one.</p>'
		+ manual('Concepts#earth-engine-data-by-its-id'),
	'asset_unit':
		'<p>The unit of the values, after the scale and the offset, written in '
		'<a href="https://docs.unidata.ucar.edu/udunits/current/">UDUNITS</a> (the units of the CF conventions): '
		'<code>mm</code>, <code>degC</code>, <code>K</code>, <code>kg m-2</code>, <code>mm day-1</code>, '
		'<code>W m-2</code>, or <code>1</code> if dimensionless. It goes to the CSV, the README and the GeoTIFF of the '
		'results; empty, they say that no unit was given.</p>'
		'<p><b>Read</b> fills it when the record of the Earth Engine data catalog gives it in a unit that MonitorEO '
		'knows; otherwise the empty field shows what the record says.</p>'
		+ manual('Concepts#earth-engine-data-by-its-id'),
	'where':
		'<p>Only the pixels of the region whose variables pass these conditions (both, if both are checked): e.g. '
		'<b>ELEVATION · Copernicus</b> between 1500 and an empty max keeps the pixels above 1,500 m, and <b>SLOPE · '
		'Copernicus</b> with max 20, those with slopes under 20°. Give a min, a max or both, in the unit shown.</p>'
		'<p>A variable with dates (NDVI, PRECIP...) is its mean over the <b>Period</b> above, the same pixels for '
		'every step of a series or a trend, and for both periods of a comparison. Series, maps, trends, comparisons '
		'and exports keep only those pixels, and their README says which.</p>'
		+ manual('Concepts#filtering-the-study-area'),
	'filters':
		'<p>Removes from each image, before computing, the pixels that its quality bands mark with clouds (and their '
		'shadows), water, snow or many aerosols. Each product has its own bands: aerosols can only be removed in '
		'Landsat 8 and 9 and in the NDVI, EVI and LAI of MODIS.</p>'
		'<p>Uncheck the filter of what the variable measures: <b>snow</b> with the NDSI and <b>water</b> with the '
		'NDWI, the Chl-a and the NDCI.</p>',
	'cloud_score':
		'<p>Only for Sentinel-2, and with the check box <b>clouds</b> checked. Checked, clouds are removed with '
		'Google\'s Cloud Score+: a pixel is clear if its score is at least 0.6. Unchecked, with the scene '
		'classification (SCL) of Sentinel-2: shadows, clouds and cirrus.</p>'
		+ manual('Concepts#per-pixel-filters'),
	'step':
		'<p>How often the series gives a value: <b>Monthly</b>, <b>Annual</b>, <b>16 days</b> (blocks of 16 days from '
		'January 1 of each year) or <b>Daily</b> (each day with images). Long steps take less time and have fewer gaps '
		'because of clouds.</p><p>To compare periods: monthly, 16 days or annual.</p>'
		+ manual('Concepts#from-the-pile-of-images-to-a-number-metric-and-statistic'),
	'ts_metric':
		'<p>How the images of each step are summarized on each pixel: with the step Monthly and <b>Mean</b>, the mean '
		'of the images of each month. The median and the percentiles resist outliers better, such as clouds that '
		'escape the filters.</p>'
		+ manual('Concepts#from-the-pile-of-images-to-a-number-metric-and-statistic'),
	'stat':
		'<p>How the pixels of the region (of each polygon) are summarized in one value per step, after the metric of '
		'each step. The <b>Standard deviation</b> measures how different the pixels are from each other.</p>'
		'<p>It is also the statistic of the <b>Trend table of the region</b> and of the comparison of periods.</p>'
		+ manual('Concepts#from-the-pile-of-images-to-a-number-metric-and-statistic'),
	'series_list':
		'<p>Time series, trend tables, comparisons and burn severities computed in this QGIS session. Choose one and '
		'press <b>Show</b> to open its window again, with its chart (if it has one), its table and the buttons to save '
		'them: <b>Save CSV…</b>, <b>Save chart…</b> and, for a burn severity, <b>Save GeoTIFF…</b>.</p>'
		'<p>In the window of a time series, <b>Map of</b> and <b>Add to the map</b> add the map of its whole period or '
		'of one of its dates, with its days in the Temporal Controller. If the images of the variable have a true '
		'colour (Sentinel-2, Landsat and the cloud frequency of MODIS), <b>Layer</b> chooses the <b>Index</b>, its '
		'<b>True colour (RGB)</b>, the red, green and blue reflectance of the same images and pixels, or <b>Both</b>, '
		'the true colour under the index. The true colours of a series are stretched as its first one, so that its '
		'dates can be compared.</p>'
		'<p>The list is lost when QGIS is closed: save what you want to keep.</p>'
		+ manual('QGIS-plugin#5-compute-the-time-series'),
	'trend_step':
		'<p>Parts of the year whose trend is computed over the years of the period: <b>Year</b> (the whole year, or '
		'the season if it is checked), <b>Months</b> (each of the 12) or <b>16 days</b> (23 blocks from January 1). '
		'Each year gives a value of each part; with those values, the Mann-Kendall test tells whether there is a trend, '
		'and Sen\'s slope, how much the variable changes per year.</p>'
		'<p>At least 2 years are needed, and better 8 or more: for long series, Landsat or MODIS.</p>'
		+ cite_html(method_references('trends')) + manual('Concepts#seasonal-trends-mann-kendall-and-sen'),
	'trend_metric':
		'<p>How the images of each part of the year are summarized in each year: with <b>Months</b> and <b>Mean</b>, '
		'the mean of the images of each July. In the table, that value is computed for the region with the '
		'<b>Statistic of the region</b> of the group Time series; in the map, on each pixel.</p>'
		+ manual('Concepts#seasonal-trends-mann-kendall-and-sen'),
	'trend_part':
		'<p>The part of the year that the <b>Trend map</b> paints: a month or a block of 16 days (with <b>Year</b>, '
		'the whole year).</p>'
		'<p>The map has six bands per pixel: Sen\'s slope (the one painted, from red, decrease, to green, increase), '
		'Kendall\'s τ, Z, p-value, intercept (the value of the line in the first year) and number of years with data. '
		'Query them with <b>Identify Features</b>.</p>'
		+ manual('QGIS-plugin#6-trends'),
	'trend_alpha':
		'<p>Checked, the trend map only shows the pixels with a significant trend (p-value &lt; 0.05); the others are '
		'left with no data. Unchecked, it shows all of them.</p>'
		'<p>A high p-value does not prove that there is no change: with few years or much variability, the test has no '
		'power to see it.</p>' + manual('Concepts#seasonal-trends-mann-kendall-and-sen'),
	'map_metric':
		'<p>How the images of the period (or of each year or month, according to the <b>Temporal aggregation</b>) are '
		'summarized on each pixel. The <b>Median</b> resists outliers better than the mean.</p>'
		'<p>With <b>Compare with</b> checked, it is computed in the two periods and the layer is their difference.</p>'
		+ manual('Concepts#maps-aggregation-over-time'),
	'temporal':
		'<ul><li><b>Whole period</b>: the metric of all the images of the period.</li>'
		'<li><b>Each year, then between years</b>: the metric of each year and, then, the <b>Metric between years</b> '
		'of those values. With Maximum and Median, the median of the annual maxima.</li>'
		'<li><b>Each month, then between years</b>: the metric of each month; then, the metric between years of each '
		'month of the calendar (e.g. the mean of all the Julys) and, at the end, the mean of those months.</li></ul>'
		+ manual('Concepts#maps-aggregation-over-time'),
	'interannual':
		'<p>Only with <b>Each year, then between years</b> or <b>Each month, then between years</b>: how the values of '
		'the different years are combined. With <b>Whole period</b> it is not used.</p>'
		+ manual('Concepts#maps-aggregation-over-time'),
	'map_kind':
		'<p>What <b>Add the layer to the map</b> adds:</p><ul>'
		'<li><b>Index</b>: the map of the variable, with its values.</li>'
		'<li><b>True colour (RGB)</b>: the red, green and blue surface reflectance of the same images (sensor, period, '
		'season and pixel filters) and of the same pixels as the index (also those of <b>Only the pixels where</b>), '
		'with the same <b>Metric</b>, <b>Temporal aggregation</b> and <b>Metric between years</b>: a GeoTIFF with the '
		'bands red, green and blue, the three stretched together between their percentiles 2 and 98, so that the '
		'colours keep their balance. With <b>Minimum</b> and <b>Maximum</b>, the colours of the image where the '
		'variable is lowest or highest on each pixel.</li>'
		'<li><b>Both</b>: the true colour and, on top of it, the index, on the same pixels.</li></ul>'
		'<p>Only the variables of Sentinel-2 and Landsat and the cloud frequency of MODIS have a true colour: not the '
		'fixed layers, the climate, the other products of MODIS (their NDVI and EVI have no green band), the data of '
		'Earth Engine given by their ID nor the difference of <b>Compare with</b>.</p>'
		+ manual('QGIS-plugin#4-add-the-map'),
	'resolution':
		'<p>Pixel size of the GeoTIFF of <b>Map (GeoTIFF)</b>, in meters. With 0, <i>that of the data</i>: 10 m in '
		'Sentinel-2, 30 m in Landsat and from 250 m to 4.6 km in MODIS. A bigger pixel gives a smaller file and a '
		'faster export.</p>'
		'<p>The layers of <b>Add the layer to the map</b> do not use it: they have the resolution of the data up to 4 '
		'million pixels and, in bigger regions, bigger pixels.</p>' + manual('QGIS-plugin#8-export-to-google-drive'),
	'folder':
		'<p>Folder of your Google Drive where Earth Engine leaves the files; if it does not exist, Earth Engine makes '
		'it. The exports have no size limit and go on in Earth Engine even if you close QGIS. The panel follows each '
		'task and tells you when it ends; with Google Drive for desktop, the GeoTIFF is added to the project as soon as '
		'it is synced.</p>'
		'<p>Exporting needs your Google account and your project (above, in <b>Project</b>): the shared account of '
		'MonitorEO cannot export, because the files go to the Google Drive of the account that computes.</p>'
		'<p>The map uses the options of the group <b>Map</b>, and the series, those of the group <b>Time '
		'series</b>.</p>'
		+ manual('QGIS-plugin#8-export-to-google-drive'),
	'fire_sensor':
		'<p>The images of the burn severity: <b>Sentinel-2</b> (10 m, since 2017) or <b>Landsat</b> (30 m, since 1984, '
		'for old fires). With the index RBR, Sentinel-2 uses its bands B8A and B12, of 20 m.</p>'
		'<p>It uses the pixel filters of the group <b>Variable</b> (<b>Remove pixels with</b>; those you chose, also '
		'while a variable with fixed filters greys them out) and its conditions of '
		'<b>Only the pixels where</b>, over the period before the fire. The region is that of the group '
		'<b>Region</b>; in big regions (more than 4 million pixels), it uses bigger pixels, as the maps.</p>'
		+ manual('QGIS-plugin#9-burn-severity-of-a-fire'),
	'fire_index':
		'<ul><li><b>dNBR</b>: NBR before the fire minus NBR after it, in the 7 classes of the USGS (Key &amp; Benson '
		'2006), from enhanced regrowth to high severity. The window gives the hectares of each class over each '
		'feature of the region and the burned area (dNBR ≥ 0.1); the layer, the band <i>severity</i> with the colour '
		'of each class.</li>'
		'<li><b>RBR</b> (Relativized Burn Ratio, Parks et al. 2014): dNBR / (NBR before + 1.001), a continuous index '
		'without classes, also for vegetation that was sparse before the fire; without phenological correction and '
		'without the factor 1000 of the articles. The window gives its mean, median, percentiles 10 and 90, minimum and '
		'maximum; the layer, from red (burned) to green (regrowth), from -0.5 to 0.5.</li></ul>'
		'<p>The GeoTIFF also has the bands dnbr, nbr_before and nbr_after (query them with <b>Identify '
		'Features</b>).</p>'
		+ cite_html(method_references('burn_severity') + method_references('rbr'))
		+ manual('Concepts#burn-severity-dnbr'),
	'fire_before':
		'<p>A period <b>before the fire</b>, without it: the median of its images on each pixel is the NBR before. A '
		'few weeks or months of the same season, e.g. the 2 months before the fire, so that clouds leave clear '
		'images.</p>'
		+ manual('QGIS-plugin#9-burn-severity-of-a-fire'),
	'fire_after':
		'<p>A period <b>after the fire</b>, once it is out: the median of its images is the NBR after. The 1 or 2 '
		'months after it ends measure the first effects; a year later (the same season), the effects that last.</p>'
		'<p>At first, those of the example of the manual: the fire of August 2023 in Teide National Park.</p>'
		+ manual('QGIS-plugin#9-burn-severity-of-a-fire'),
}


def describe(v):
	"""Description of the catalog of V, an item of services.list_variables, with the English names of the catalog."""
	return services.describe_variable(v['variable'], v['sensor'], v['collection'], lang='en')


def filter_lines(v, d):
	"""The filters that can be applied to V (described by D) and those that remove what it measures."""
	names = [FILTER_NAMES[f] for f in sensors.FILTERS if d['pixel_filters'].get(f)]
	if d.get('static'):  # elevation, slope: an image, without filters
		return [f"{v['variable']} of {v['sensor']} has no pixel filters: it is a fixed layer, without dates."]
	if d.get('fixed_filters') is not None:  # the snow cover frequency: always without clouds and water
		return [f"{v['variable']} of {v['sensor']} has fixed filters, which cannot be changed: it always removes "
		        f"{' and '.join(names)}."]
	out = [f"With {v['variable']} of {v['sensor']} you can remove: {', '.join(names) or 'no filter'}."]
	for f in d['measures']:
		if d['pixel_filters'].get(f):
			out.append(f"<b>{v['variable']} measures {MEASURED[f]}: uncheck {FILTER_NAMES[f]}</b>, or it will remove "
			           "it.")
	return out


def data_use(d):
	"""How the panel can use the data D read (services.describe_asset), in the words of its list Use as (the 'how' of
	describe_asset gives the arguments of the services instead): an image, only as a fixed image; a collection with
	dates, as images with dates or as the mosaic of its images; a collection without dates (tiles), as their mosaic."""
	if d.get('type') == 'image':
		return 'an image: use it as Fixed image (image), only its maps and their statistics'
	if d.get('use') == 'collection':
		return ('a collection of images with dates: use it as Images with dates (collection), with maps, time series, '
		        'trends and comparisons, or as Fixed image (image), the mosaic of its images')
	return 'a collection of images without dates (tiles): use it as Fixed image (image), the mosaic of its tiles'


def data_summary(d, read=True):
	"""What the panel says under the options of the data of Earth Engine D (services.describe_asset; without READ,
	the record of a dataset of the GEE Community Catalog not read yet): its title, source, provider, licence and page,
	its dates and how it is used (data_use)."""
	parts = [x for x in (d.get('source'), d.get('provider'), d.get('licence') and f"licence {d['licence']}") if x]
	line = f"<b>{esc(d.get('title') or d.get('asset') or '')}</b>" + ''.join(f' · {esc(x)}' for x in parts)
	if d.get('page'):
		line += f""" · <a href="{esc(d['page'])}">its page</a>"""
	lines = [line]
	dates = d.get('dates') or [None, None]
	if dates[0]:
		lines.append(f"Dates: {esc(dates[0])} to {esc(dates[1])}" if dates[1] else f"Dates: from {esc(dates[0])}")
		if d.get('cadence'):
			lines[-1] += f", every {esc(d['cadence'])}"
	if not read:
		lines.append('Reading its bands in Earth Engine…')
	elif d.get('type'):
		use = data_use(d)
		lines.append(esc(use[:1].upper() + use[1:]) + '.')
	return '<br>'.join(lines)


def band_lines(b):
	"""What the record of the data says of the band B (one of the bands of services.describe_asset)."""
	lines = []
	what = [b.get('description'), b.get('units') and f"unit in its record: {b['units']}",
	        b.get('resolution_m') and f"pixel of {b['resolution_m']:g} m", b.get('data_type')]
	if any(what):
		lines.append(f"Band {esc(b['band'])}: " + '; '.join(esc(x) for x in what if x) + '.')
	classes = b.get('classes') or {}
	if classes:
		shown = '; '.join(f'{esc(k)} {esc(v)}' for k, v in list(classes.items())[:12])
		lines.append(f"Classes: {shown}" + ('; and more.' if len(classes) > 12 else '.'))
	return lines


def data_help(v, info=None):
	"""Help of the data of Earth Engine given by their ID: with V the entry of those data in the list Variable of the
	panel (dock.custom_entry), what is chosen and, once read (INFO: what services.describe_asset said of it), what its
	record says of it and of its band, its notes and how to cite it; then the general text. With a variable of the
	catalog, the general text."""
	v = v or {}
	if not v.get('custom') or not v.get('asset'):
		return HELP['asset']
	band = v.get('band')
	use = 'images with dates (collection)' if v.get('use') == 'collection' else 'a fixed image (image)'
	lines = [f"<b>{esc(v['asset'])}</b>" + (f", band <b>{esc(band)}</b>" if band else ', no band chosen') +
	         f", as {use}.",
	         f"Values: stored × {esc(v.get('band_scale') or '1')} + {esc(v.get('band_offset') or '0')}; unit: "
	         f"{esc(v.get('unit') or 'not given')}. No pixel filters: these data keep only their own mask."]
	if v.get('static'):
		lines.append('<b>A fixed image, without dates</b>: only its map (Map and Export to Google Drive); the period, '
		             'the metrics, the time series and the trends do not apply.')
	refs, credits = (), ()
	if info:
		lines.append(data_summary(info))
		for b in info.get('bands') or []:
			if b.get('band') == band:
				lines += band_lines(b)
		lines += [esc(n) for n in info.get('notes') or []]
		refs, credits = info.get('references') or (), info.get('credits') or ()
	else:
		lines.append('Press <b>Read</b> to see what it is, its bands and how to cite it.')
	return ''.join(f'<p>{line}</p>' for line in lines) + \
		cite_html(refs, credits, 'References of its data (cite them with its results)') + HELP['asset']


def variable_help(v, info=None):
	"""Help of the variable: the general text and the variable V chosen (the data of Earth Engine given by their ID:
	data_help, with INFO, what services.describe_asset said of them)."""
	if (v or {}).get('custom'):
		return data_help(v, info)
	d = describe(v)
	lines = [f"<b>{v['variable']} · {v['sensor']}</b>: {d['name']} ({d['group']}).",
	         f"Unit: {v['unit'].strip('[]')}. Pixel of {v['resolution_m']} m. Dates: "
	         f"{v['dates']}. Collection: {v['collection']}."] + filter_lines(v, d)
	if d.get('metric'):  # the snow cover frequency: how it is computed, and its only metric
		lines += [d['notes'].get('ft', ''), f"<b>Only with the metric {d['metric']}</b>: {d['notes'].get('metric', '')}."]
	if d.get('static'):  # elevation, slope: only maps
		lines += [d['notes'].get('ft', ''), '<b>A fixed layer, without dates</b>: only its map (Map and Export to Google '
		          'Drive); the period, the metrics, the time series and the trends do not apply.']
	return HELP['variable'] + ''.join(f'<p>{line}</p>' for line in lines) + \
		cite_html(d.get('references'), d.get('credits'),
		          'References of its formula and its data (cite them with its results)') + \
		manual('Concepts#variables')


def filters_help(v):
	"""Help of the pixel filters, with those of the variable V chosen (none for the data of Earth Engine given by
	their ID)."""
	if (v or {}).get('custom'):
		return HELP['filters'] + (f"<p>{esc(v.get('name') or 'These data')}: the data of Earth Engine outside the "
		                          'catalog keep only their own mask (e.g. that of their missing values); the pixel '
		                          'filters are for the variables of the catalog.</p>') + \
			manual('Concepts#earth-engine-data-by-its-id')
	lines = filter_lines(v, describe(v))
	return HELP['filters'] + ''.join(f'<p>{line}</p>' for line in lines) + manual('Concepts#per-pixel-filters')
