// PROTOTYPE — throwaway. Thin Data Studio community connector for the BSL prototype API.
// Paste into an Apps Script project (script.google.com), set the manifest from appsscript.json, deploy.
var cc = DataStudioApp.createCommunityConnector();

function getAuthType() {
  return cc.newAuthTypeResponse().setAuthType(cc.AuthType.NONE).build();
}

function isAdminUser() { return true; }

function getConfig() {
  var config = cc.getConfig();
  config.newTextInput().setId('apiUrl').setName('API base URL').setPlaceholder('https://example.com');
  config.setDateRangeRequired(true);
  return config.build();
}

function fetchJson(url, body) {
  var opts = {muteHttpExceptions: true, contentType: 'application/json'};
  if (body) { opts.method = 'post'; opts.payload = JSON.stringify(body); }
  var res = UrlFetchApp.fetch(url, opts);
  if (res.getResponseCode() !== 200) {
    cc.newUserError().setText('API error ' + res.getResponseCode() + ': ' + res.getContentText().slice(0, 200)).throwException();
  }
  return JSON.parse(res.getContentText());
}

// Builds fields with the documented builder (D-22): formulas use $ references.
function buildFields(schema) {
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
  var schema = fetchJson(request.configParams.apiUrl + '/schema').schema;
  return {schema: buildFields(schema).build()};
}

function getData(request) {
  // PROTOTYPE fog tests (no API, no tunnel). B: PAR_SLEEP_MS > 0 sleeps every getData to expose parallelism.
  var PAR_SLEEP_MS = 0;
  if (PAR_SLEEP_MS) Utilities.sleep(PAR_SLEEP_MS);
  // A: a chart with exactly airports.country x min_delay gets SYN_ROWS synthetic rows built like an API response.
  var SYN_ROWS = 0;  // set >0 to re-run the row-limit test (1,000,000 ok; 1,500,000 rejected)
  var names = request.fields.map(function (f) { return f.name; });
  if (SYN_ROWS && names.length === 2 && names.indexOf('airports__country') >= 0 && names.indexOf('min_delay') >= 0) {
    var rows = [], ci = names.indexOf('airports__country');
    for (var i = 0; i < SYN_ROWS; i++) { var vals = [null, null]; vals[ci] = 'c' + ('000000' + i).slice(-7); vals[1 - ci] = i % 997; rows.push({values: vals}); }
    var parsed = JSON.parse(JSON.stringify({rows: rows}));
    var f = cc.getFields();
    request.fields.forEach(function (rf) {
      if (rf.name === 'airports__country') f.newDimension().setId('airports__country').setName('airports.country').setType(cc.FieldType.TEXT);
      else f.newMetric().setId('min_delay').setName('min_delay').setType(cc.FieldType.NUMBER).setAggregation(cc.AggregationType.MIN);
    });
    return {schema: f.build(), rows: parsed.rows, filtersApplied: false};
  }
  // PROTOTYPE U-16: how long does Data Studio wait for getData? Only for a chart that requests exactly max_delay.
  var U16_DELAY_MS = 0;  // set to e.g. 330000 to re-run the U-16 timeout test
  if (U16_DELAY_MS && request.fields.length === 1 && request.fields[0].name === 'max_delay') {
    var t0 = Date.now();
    while (Date.now() - t0 < U16_DELAY_MS) Utilities.sleep(Math.min(60000, U16_DELAY_MS - (Date.now() - t0)));
    var f = cc.getFields();
    f.newMetric().setId('max_delay').setName('max_delay').setType(cc.FieldType.NUMBER).setAggregation(cc.AggregationType.MAX);
    return {schema: f.build(), rows: [{values: [119]}], filtersApplied: false};
  }
  var apiUrl = request.configParams.apiUrl;
  var res = fetchJson(apiUrl + '/data', request); // /data returns the schema for the requested ids
  return {schema: buildFields(res.schema).build(), rows: res.rows, filtersApplied: res.filtersApplied};
}
