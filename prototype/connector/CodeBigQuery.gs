// PROTOTYPE — throwaway. Wayfinder #21: BigQuery advanced services with the BSL schema.
// Manifest: appsscript.bigquery.json (advancedServices.schema false, data true; bigquery.readonly scope).
// getSchema: the normal BSL schema from the API (/bq/schema) with descriptions, formulas, hidden helpers.
// getData:   returns newBigQueryConfig(); Data Studio runs the SQL in BigQuery itself.
// Config "mode":
//   A      base relation (one SQL per model, request-independent) from /bq/sql?shape=A
//   A_CACHED  same SQL, cached in CacheService for 6 h: getData makes no URL Fetch (lowest overhead)
//   B      per-request BSL query from /bq/sql?shape=B (needs a getData call per chart)
//   ROWS   the current path (/data rows) - tests whether getData may return rows in this mode
// Every getData logs one line "BQ21 {...}" (Executions page): mode, request fields, filters, date range, ms.
var cc = DataStudioApp.createCommunityConnector();
var props = PropertiesService.getUserProperties();

function getAuthType() {
  return cc.newAuthTypeResponse().setAuthType(cc.AuthType.PATH_KEY).setHelpUrl('https://example.com').build();
}
function setCredentials(request) {
  var path = (request.pathKey.path || '').replace(/\/+$/, ''), key = request.pathKey.key;
  var res = UrlFetchApp.fetch(path + '/bq/schema', {headers: {'X-API-Key': key}, muteHttpExceptions: true});
  if (res.getResponseCode() !== 200) return {errorCode: 'INVALID_CREDENTIALS'};
  props.setProperty('bsl.path', path); props.setProperty('bsl.key', key);
  return {errorCode: 'NONE'};
}
function isAuthValid() { return !!(props.getProperty('bsl.path') && props.getProperty('bsl.key')); }
function resetAuth() { props.deleteProperty('bsl.path'); props.deleteProperty('bsl.key'); }
function isAdminUser() { return true; }

function getConfig() {
  var config = cc.getConfig();
  config.newTextInput().setId('billingProject').setName('BigQuery billing project ID')
    .setHelpText('The query runs as you (bigquery.readonly) and is billed to this project. You need roles/bigquery.jobUser there.');
  config.newSelectSingle().setId('mode').setName('Mode')
    .addOption(config.newOptionBuilder().setLabel('A: base relation').setValue('A'))
    .addOption(config.newOptionBuilder().setLabel('A: base relation, SQL cached (no URL Fetch)').setValue('A_CACHED'))
    .addOption(config.newOptionBuilder().setLabel('B: per-request BSL query').setValue('B'))
    .addOption(config.newOptionBuilder().setLabel('ROWS: current /data path').setValue('ROWS'));
  config.setDateRangeRequired(true);
  return config.build();
}

function fetchJson(url, body) {
  var opts = {muteHttpExceptions: true, contentType: 'application/json', headers: {'X-API-Key': props.getProperty('bsl.key')}};
  if (body) { opts.method = 'post'; opts.payload = JSON.stringify(body); }
  var res;
  try { res = UrlFetchApp.fetch(url, opts); }
  catch (e) { cc.newUserError().setText('BSL API unreachable: ' + e).throwException(); }
  if (res.getResponseCode() !== 200) cc.newUserError().setText('API error ' + res.getResponseCode() + ': ' + res.getContentText().slice(0, 200)).throwException();
  return JSON.parse(res.getContentText());
}

function buildFields(schema) {  // same builder as Code.gs
  var fields = cc.getFields();
  schema.forEach(function (f) {
    var fld = f.type === 'DIMENSION' ? fields.newDimension() : fields.newMetric();
    fld.setId(f.id).setName(f.name).setDescription(f.description || '');
    fld.setType(cc.FieldType[f.semanticType || (f.dataType === 'NUMBER' ? 'NUMBER' : 'TEXT')]);
    if (f.aggregation) fld.setAggregation(cc.AggregationType[f.aggregation]);
    if (f.formula) fld.setFormula(f.formula);
    if (f.isHidden) fld.setIsHidden(true);
    if (f.isReaggregatable === false) fld.setIsReaggregatable(false);
  });
  return fields;
}

function getSchema(request) {
  return {schema: buildFields(fetchJson(props.getProperty('bsl.path') + '/bq/schema').schema).build()};
}

function getData(request) {
  var t0 = Date.now(), mode = (request.configParams && request.configParams.mode) || 'A', sql, out;
  var api = props.getProperty('bsl.path');
  if (mode === 'ROWS') {
    var res = fetchJson(api + '/data', request);
    out = {schema: buildFields(res.schema).build(), rows: res.rows, filtersApplied: res.filtersApplied};
  } else {
    if (mode === 'A_CACHED') {
      var cache = CacheService.getScriptCache();
      sql = cache.get('bq21.sqlA');
      if (!sql) { sql = fetchJson(api + '/bq/sql?shape=A', request).sql; cache.put('bq21.sqlA', sql, 21600); }
    } else {
      sql = fetchJson(api + '/bq/sql?shape=' + mode, request).sql;
    }
    out = cc.newBigQueryConfig()
      .setBillingProjectId(request.configParams.billingProject)
      .setQuery(sql)
      .setUseStandardSql(true)
      .setAccessToken(ScriptApp.getOAuthToken())
      .build();
  }
  console.log('BQ21 ' + JSON.stringify({
    mode: mode, ms: Date.now() - t0,
    fields: request.fields.map(function (f) { return f.name + (f.forFilterOnly ? '(filter)' : ''); }),
    filters: request.dimensionsFilters || null, dateRange: request.dateRange || null,
    sampleExtraction: !!(request.scriptParams && request.scriptParams.sampleExtraction)
  }));
  return out;
}
