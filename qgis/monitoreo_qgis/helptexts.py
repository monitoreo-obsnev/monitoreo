"""Help of the options of the MonitorEO panel, shown by their buttons ⓘ: short texts in English (rich text of Qt),
each ending with a link to the section of the manual (the English pages of the wiki of the repository) that explains
it. The help of the variable and of the pixel filters also describes the variable chosen (variable_help,
filters_help)."""

from . import deps

deps.setup_path()
from monitoreo import about, sensors, services  # noqa: E402

MANUAL = f'{about.MANUAL}/QGIS-plugin'  # the English page of the plugin in the wiki
FILTER_NAMES = {'clouds': 'clouds', 'water': 'water', 'snow': 'snow', 'aerosols': 'aerosols'}
MEASURED = {'water': 'water', 'snow': 'snow', 'aerosols': 'aerosols'}


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
		'<li><b>Ecoregion at the center of the map</b>: the RESOLVE 2017 ecoregion that contains the center of the '
		'view.</li></ul>' + manual('Concepts#regions'),
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
		'up to 30 areas of the <a href="https://www.protectedplanet.net">WDPA</a> with that text in their name.</p>'
		+ manual('QGIS-plugin#2-choose-the-region'),
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
		'<p>Time series, trend tables and comparisons computed in this QGIS session. Choose one and press <b>Show</b> '
		'to open its window again, with the chart, the table and the buttons <b>Save CSV…</b> and <b>Save '
		'chart…</b>.</p><p>The list is lost when QGIS is closed: save what you want to keep.</p>'
		+ manual('QGIS-plugin#5-compute-the-time-series'),
	'trend_step':
		'<p>Parts of the year whose trend is computed over the years of the period: <b>Year</b> (the whole year, or '
		'the season if it is checked), <b>Months</b> (each of the 12) or <b>16 days</b> (23 blocks from January 1). '
		'Each year gives a value of each part; with those values, the Mann-Kendall test tells whether there is a trend, '
		'and Sen\'s slope, how much the variable changes per year.</p>'
		'<p>At least 2 years are needed, and better 8 or more: for long series, Landsat or MODIS.</p>'
		+ manual('Concepts#seasonal-trends-mann-kendall-and-sen'),
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


def variable_help(v):
	"""Help of the variable: the general text and the variable V chosen."""
	d = describe(v)
	lines = [f"<b>{v['variable']} · {v['sensor']}</b>: {d['name']} ({d['group']}).",
	         f"Unit: {v['unit'].strip('[]')}. Pixel of {v['resolution_m']} m. Dates: "
	         f"{v['dates']}. Collection: {v['collection']}."] + filter_lines(v, d)
	if d.get('metric'):  # the snow cover frequency: how it is computed, and its only metric
		lines += [d['notes'].get('ft', ''), f"<b>Only with the metric {d['metric']}</b>: {d['notes'].get('metric', '')}."]
	if d.get('static'):  # elevation, slope: only maps
		lines += [d['notes'].get('ft', ''), '<b>A fixed layer, without dates</b>: only its map (Map and Export to Google '
		          'Drive); the period, the metrics, the time series and the trends do not apply.']
	return HELP['variable'] + ''.join(f'<p>{line}</p>' for line in lines) + manual('Concepts#variables')


def filters_help(v):
	"""Help of the pixel filters, with those of the variable V chosen."""
	lines = filter_lines(v, describe(v))
	return HELP['filters'] + ''.join(f'<p>{line}</p>' for line in lines) + manual('Concepts#per-pixel-filters')
