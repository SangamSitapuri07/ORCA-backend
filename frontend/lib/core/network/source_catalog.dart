/// Model describing an external data source in the catalog (§5, §11).
class SourceDescriptor {
  final String healthKey;
  final String name;
  final String agency;
  final String host;
  final String authType;
  final String purpose;
  final String defaultNote;

  const SourceDescriptor({
    required this.healthKey,
    required this.name,
    required this.agency,
    required this.host,
    required this.authType,
    required this.purpose,
    required this.defaultNote,
  });
}

/// Authoritative 17-source catalog mapping to /api/v1/health source_health.
class SourceCatalog {
  static const List<SourceDescriptor> all = <SourceDescriptor>[
    SourceDescriptor(
      healthKey: 'open_meteo_marine',
      name: 'Open-Meteo Marine',
      agency: 'Open-Meteo upstream marine models',
      host: 'marine-api.open-meteo.com',
      authType: 'None',
      purpose: 'Hourly wave height, swell period, SST, ocean currents (96h horizon)',
      defaultNote: 'Fetch-on-demand marine forecast capability',
    ),
    SourceDescriptor(
      healthKey: 'open_meteo_forecast',
      name: 'Open-Meteo Forecast',
      agency: 'Open-Meteo upstream forecast models',
      host: 'api.open-meteo.com',
      authType: 'None',
      purpose: 'Hourly wind speed, 48h WMO 34kn gale gusts, precipitation',
      defaultNote: 'Fetch-on-demand atmospheric forecast capability',
    ),
    SourceDescriptor(
      healthKey: 'open_meteo_daily',
      name: 'Open-Meteo Daily',
      agency: 'Open-Meteo upstream forecast models',
      host: 'api.open-meteo.com',
      authType: 'None',
      purpose: 'Daily WMO weather codes and sky conditions',
      defaultNote: 'Daily WMO sky codes',
    ),
    SourceDescriptor(
      healthKey: 'open_meteo_archive',
      name: 'Open-Meteo Archive',
      agency: 'Open-Meteo Historical',
      host: 'archive-api.open-meteo.com',
      authType: 'None',
      purpose: 'Three-prior-year date-window sample for a provisional SST deviation flag',
      defaultNote: 'Not a 30-year climatology or heatwave diagnosis',
    ),
    SourceDescriptor(
      healthKey: 'noaa_coastwatch',
      name: 'NOAA CoastWatch ERDDAP',
      agency: 'US NOAA NESDIS',
      host: 'coastwatch.noaa.gov',
      authType: 'None',
      purpose: 'Satellite chlorophyll-a with today → 3d → 7d DINEOF lag chain',
      defaultNote: 'Satellite chlorophyll capability; status comes from ORCA Box',
    ),
    SourceDescriptor(
      healthKey: 'esa_oc_cci',
      name: 'ESA OC-CCI v6',
      agency: 'European Space Agency',
      host: 'comet.nefsc.noaa.gov',
      authType: 'None',
      purpose: 'Optional independent chlorophyll comparison',
      defaultNote: 'Unavailable comparisons stay unavailable; ORCA does not assume the cause',
    ),
    SourceDescriptor(
      healthKey: 'isro_mosdac',
      name: 'ISRO MOSDAC OCM-3',
      agency: 'ISRO / Space Applications Centre',
      host: 'mosdac.gov.in',
      authType: 'Govt SSO (.env)',
      purpose: 'EOS-06 OCM-3 L2C LAC ocean-colour granules with a bounded live chain',
      defaultNote: 'Requires configured MOSDAC credentials',
    ),
    SourceDescriptor(
      healthKey: 'incois_erddap',
      name: 'INCOIS ERDDAP',
      agency: 'MoES / INCOIS Hyderabad',
      host: 'erddap.incois.gov.in',
      authType: 'None',
      purpose: 'Catalogued regional endpoint; no chlorophyll adapter is currently wired',
      defaultNote: 'Not integrated into the current ORCA data path',
    ),
    SourceDescriptor(
      healthKey: 'incois_las',
      name: 'INCOIS LAS',
      agency: 'INCOIS Live Access Server',
      host: 'las.incois.gov.in',
      authType: 'None',
      purpose: 'OCM-2 chlorophyll OPeNDAP hyperslab fallback',
      defaultNote: 'Conditional backup; the 2026-09-12 audit returned NetCDF I/O failure in this runtime',
    ),
    SourceDescriptor(
      healthKey: 'incois_pfz',
      name: 'INCOIS PFZ GeoServer',
      agency: 'MoES / INCOIS Hyderabad',
      host: 'incois.gov.in',
      authType: 'None (WFS)',
      purpose: 'Official daily Potential Fishing Zone line geometry',
      defaultNote: 'Official PFZ WFS fetched on demand',
    ),
    SourceDescriptor(
      healthKey: 'gfw_ais',
      name: 'Global Fishing Watch',
      agency: 'Global Fishing Watch',
      host: 'gateway.api.globalfishingwatch.org',
      authType: 'API Token',
      purpose: 'AIS-derived apparent fishing hours and fleet grouping in a requested region',
      defaultNote: 'Requires configured GFW token',
    ),
    SourceDescriptor(
      healthKey: 'jtwc_cyclone',
      name: 'JTWC (US Navy)',
      agency: 'Joint Typhoon Warning Center',
      host: 'www.metoc.navy.mil',
      authType: 'None',
      purpose: 'Supplemental US DoD cyclone guidance; IMD remains India’s official authority',
      defaultNote: 'JTWC bulletins fetched on demand when reachable',
    ),
    SourceDescriptor(
      healthKey: 'marine_regions_eez',
      name: 'MarineRegions WFS',
      agency: 'Flanders Marine Institute (VLIZ)',
      host: 'geo.vliz.be',
      authType: 'None',
      purpose: 'Optional EEZ display overlay only; not legal or safety evidence',
      defaultNote: 'Display feature fetched on demand when reachable',
    ),
    SourceDescriptor(
      healthKey: 'osm_tiles',
      name: 'OpenStreetMap Tiles',
      agency: 'OpenStreetMap contributors',
      host: 'tile.openstreetmap.org',
      authType: 'None',
      purpose: 'First-party ORCA Box base-map tile proxy',
      defaultNote: 'Display only; not an official nautical chart',
    ),
    SourceDescriptor(
      healthKey: 'openseamap_seamarks',
      name: 'OpenSeaMap Seamarks',
      agency: 'OpenSeaMap contributors',
      host: 'tiles.openseamap.org',
      authType: 'None',
      purpose: 'Optional first-party ORCA Box seamark overlay proxy',
      defaultNote: 'Display only, off by default, and not an official nautical chart',
    ),
    SourceDescriptor(
      healthKey: 'globe_landmask',
      name: 'GLOBE 1km Land Mask',
      agency: 'NOAA / Local Bundled Raster',
      host: 'local_bundled',
      authType: 'None (Offline)',
      purpose: 'Rhumb line 2km collision check & land-masking chlorophyll',
      defaultNote: 'Local GLOBE raster when dependency is installed',
    ),
    SourceDescriptor(
      healthKey: 'nominatim_osm',
      name: 'Nominatim (OSM)',
      agency: 'OpenStreetMap',
      host: 'nominatim.openstreetmap.org',
      authType: 'Polite UA',
      purpose: 'Planned harbour and coastal-place search',
      defaultNote: 'Catalogued only; no Flutter search datasource is wired',
    ),
  ];

  /// Finds a source descriptor by key.
  static SourceDescriptor? findByKey(String key) {
    for (final s in all) {
      if (s.healthKey.toLowerCase() == key.toLowerCase()) {
        return s;
      }
    }
    return null;
  }
}
