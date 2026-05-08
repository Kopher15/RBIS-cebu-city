// RBIS Cebu City — Road Concern Report Handler
// Deploy as: Extensions > Apps Script > Deploy > New deployment > Web app
//   Execute as: Me
//   Who has access: Anyone
//
// After deploying, copy the Web App URL into index.html:
//   var REPORT_ENDPOINT = 'https://script.google.com/macros/s/YOUR_ID/exec';

var SHEET_NAME = 'Reports';

function doPost(e) {
  try {
    var data = e.parameter;
    var sheet = getOrCreateSheet();

    sheet.appendRow([
      data.timestamp || new Date().toLocaleString('en-PH', {timeZone:'Asia/Manila'}),
      data.name      || '',
      data.contact   || '',
      data.roadName  || '',
      data.segId     || '',
      data.district  || '',
      data.condition || '',
      data.desc      || '',
      data.photoUrl  || ''
    ]);

    return jsonResponse({ status: 'ok' });
  } catch(err) {
    return jsonResponse({ status: 'error', message: err.message });
  }
}

function getOrCreateSheet() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = ss.getSheetByName(SHEET_NAME);
  if (!sheet) {
    sheet = ss.insertSheet(SHEET_NAME);
    sheet.appendRow([
      'Timestamp', 'Name', 'Contact', 'Road Name',
      'Segment ID', 'District', 'Condition', 'Description', 'Photo URL'
    ]);
    sheet.setFrozenRows(1);
    sheet.getRange(1, 1, 1, 9).setFontWeight('bold');
    sheet.setColumnWidth(1, 160);
    sheet.setColumnWidth(4, 200);
    sheet.setColumnWidth(8, 260);
    sheet.setColumnWidth(9, 300);
  }
  return sheet;
}

function jsonResponse(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}
