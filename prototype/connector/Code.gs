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
  var apiUrl = request.configParams.apiUrl;
  var res = fetchJson(apiUrl + '/data', request); // /data returns the schema for the requested ids
  return {schema: buildFields(res.schema).build(), rows: res.rows, filtersApplied: res.filtersApplied};
}
