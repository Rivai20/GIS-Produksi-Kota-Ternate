const map = L.map('map', {
  zoomControl: true,
  scrollWheelZoom: true,
}).setView([0.79, 127.38], 11.5);

let mapResizeTimer;
const refreshMapSize = () => {
  clearTimeout(mapResizeTimer);
  mapResizeTimer = setTimeout(() => {
    map.invalidateSize();
  }, 150);
};

window.addEventListener('load', refreshMapSize);
window.addEventListener('resize', refreshMapSize);
window.addEventListener('orientationchange', () => setTimeout(refreshMapSize, 220));

const streetLayer = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  attribution: '&copy; OpenStreetMap contributors',
});

const satelliteLayer = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
  attribution: 'Tiles &copy; Esri',
});

streetLayer.addTo(map);

const locationLabelsPane = map.createPane('locationLabels');
locationLabelsPane.style.zIndex = 700;
locationLabelsPane.style.pointerEvents = 'none';

let districtData = [];

const clusterColors = {
  1: '#7cbc63',
  2: '#f0d36d',
  3: '#ef6a5f',
};

const clusterLabels = {
  1: 'Cluster 1 - Produksi Rendah',
  2: 'Cluster 2 - Produksi Sedang',
  3: 'Cluster 3 - Produksi Tinggi',
};

const districtLayer = L.layerGroup().addTo(map);
const markerLayer = L.layerGroup().addTo(map);
const locationMarkers = [];
const markerRecords = [];
const districtRecords = [];
let locationLabelsVisible = true;
const selectedZoneTypes = new Set(['fish', 'agriculture']);
let activeCommodityMetric = 'all';
let zonesVisible = true;
let markersRendered = false;
let selectedDistrictName = 'Ternate Utara';
let commodityDetails = [];

const summaryTitle = document.getElementById('summary-title');
const summaryHead = document.getElementById('summary-head');
const summaryReset = document.getElementById('summary-reset');

function escapeHtmlText(value) {
  return String(value ?? '').replace(/[&<>"']/g, (character) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
  })[character]);
}

function getActiveProduction(district, metric = activeCommodityMetric) {
  if (metric === 'fish') {
    return { value: district.production.ikan, label: 'Produksi Perikanan' };
  }
  if (metric === 'agriculture') {
    return { value: district.production.pertanian, label: 'Produksi Pertanian' };
  }
  return { value: district.production.total, label: 'Total Produksi' };
}

function updateDistrictInfo(district, metric = activeCommodityMetric) {
  if (!district) return;
  const production = getActiveProduction(district, metric);
  document.getElementById('info-kecamatan').textContent = ': ' + district.name;
  document.getElementById('info-komoditas').textContent = ': ' + district.commodity;
  document.getElementById('info-jenis').textContent = ': ' + (metric === 'fish'
    ? 'Hasil Tangkapan Ikan'
    : metric === 'agriculture' ? 'Hasil Pertanian' : district.type_name);
  document.getElementById('info-produksi').textContent = ': ' + production.value.toLocaleString('id-ID') + ' Ton/Tahun';
  document.getElementById('info-cluster').textContent = ': ' + clusterLabels[district.cluster];
}

function populateMarkerSelect(markers) {
  const markerSelect = document.getElementById('marker-select');
  if (!markerSelect) return;
  markerSelect.innerHTML = '<option value="">Pilih titik lokasi yang tersedia</option>' + markers
    .filter((point) => point.id !== undefined)
    .map((point) => `<option value="${point.id}">${point.label} - ${point.district_name}</option>`)
    .join('');
}

function selectMarker(markerId) {
  const markerSelect = document.getElementById('marker-select');
  if (markerSelect) markerSelect.value = markerId;
}

const createMarkerIcon = (emoji, type) => {
  return L.divIcon({
    className: 'custom-div-icon',
    html: `<div class="marker-pin ${type}">${emoji}</div>`,
    iconSize: [30, 30],
    iconAnchor: [15, 15],
    popupAnchor: [0, -12],
  });
};

function renderDataset(dataset) {
  districtData = dataset.districts;
  commodityDetails = dataset.commodity_details || [];
  populateMarkerSelect(dataset.markers);
  const zoneBounds = L.featureGroup();
  if (!markersRendered) {
    dataset.markers.forEach((point) => {
      const marker = L.marker(point.coords, { icon: createMarkerIcon(point.emoji, point.type_name) }).addTo(markerLayer);
      if (point.id !== undefined) marker.on('click', () => selectMarker(point.id));
      marker.bindPopup(`<div class="custom-popup"><strong>${escapeHtmlText(point.label)}</strong>Kecamatan: ${escapeHtmlText(point.district_name)}<br>${escapeHtmlText(point.value)}</div>`);
      marker.on('click', () => {
        const domain = getCommodityType(point.type_name);
        if (!domain || !point.district_name) return;
        selectedDistrictName = point.district_name;
        updateDistrictInfo(
          districtData.find((district) => district.name === point.district_name),
          domain,
        );
        renderCommodityBreakdown(point, domain, marker);
      });
      marker.bindTooltip(point.label, {
        permanent: true,
        direction: 'top',
        offset: [0, -12],
        className: 'location-label',
        pane: 'locationLabels',
      });
      locationMarkers.push(marker);
      markerRecords.push({ marker, type: point.type_name });
    });
    markersRendered = true;
  }

  districtLayer.clearLayers();
  districtRecords.length = 0;
  districtData.forEach((district) => {
  const polygon = L.polygon(district.coords, {
    color: '#ffffff',
    weight: 2,
    opacity: 1,
    fillColor: clusterColors[district.cluster],
    fillOpacity: 0.82,
  }).addTo(districtLayer);
  districtRecords.push({ district, polygon });
  zoneBounds.addLayer(polygon);

  bindDistrictPopup(district, polygon);

  polygon.on('mouseover', function () {
    this.setStyle({ weight: 3 });
  });

  polygon.on('mouseout', function () {
    this.setStyle({ weight: 2 });
  });

  polygon.on('click', function () {
    selectedDistrictName = district.name;
    updateDistrictInfo(district);
    renderSummaryTable(districtData);
  });
  });
  updateDistrictInfo(districtData.find((district) => district.name === selectedDistrictName) || districtData[0]);
  if (zoneBounds.getLayers().length) {
    map.fitBounds(zoneBounds.getBounds().pad(0.08));
    setTimeout(() => map.invalidateSize(), 80);
  }
  renderSummaryTable(districtData);
}

function bindDistrictPopup(district, polygon) {
  const production = getActiveProduction(district);
  polygon.bindPopup(`<div class="custom-popup"><strong>${district.name}</strong>${production.label}: ${production.value.toLocaleString('id-ID')} ton<br>${clusterLabels[district.cluster]}</div>`);
}

function renderCommodityBreakdown(point, domain, marker) {
  const details = commodityDetails
    .filter((record) => record.domain === domain
      && (record.district_name === point.district_name || record.scope === 'Seluruh Kota'))
    .sort((left, right) => right.year - left.year || left.commodity.localeCompare(right.commodity, 'id'));
  const domainLabel = domain === 'fish' ? 'Perikanan' : 'Pertanian';
  summaryTitle.textContent = `Komoditas ${domainLabel} · ${point.district_name}`;
  summaryReset.hidden = false;
  summaryHead.innerHTML = '<tr><th>Kecamatan/Cakupan</th><th>Komoditas</th><th>Tahun</th><th>Produksi (Ton)</th></tr>';

  const tableBody = document.querySelector('.summary-table-wrap tbody');
  if (!details.length) {
    tableBody.innerHTML = '<tr><td colspan="4">Belum ada rincian komoditas untuk titik ini.</td></tr>';
  } else {
    tableBody.innerHTML = details.map((record) => `
      <tr>
        <td>${escapeHtmlText(record.scope === 'Seluruh Kota' ? record.scope : record.district_name)}</td>
        <td>${escapeHtmlText(record.commodity)}</td>
        <td>${record.year}</td>
        <td>${Number(record.production_ton).toLocaleString('id-ID')}</td>
      </tr>`).join('');
  }

  const popupRows = details.map((record) => `
    <tr><td>${escapeHtmlText(record.commodity)}${record.scope === 'Seluruh Kota' ? ' <small>(kota)</small>' : ''}</td>
    <td>${record.year}</td><td>${Number(record.production_ton).toLocaleString('id-ID')} ton</td></tr>`).join('');
  const popupContent = `<div class="custom-popup commodity-popup">
    <strong>${escapeHtmlText(point.label)}</strong>
    <span>Kecamatan: ${escapeHtmlText(point.district_name)}</span>
    ${details.length ? `<table class="commodity-popup-table"><tbody>${popupRows}</tbody></table>` : '<span>Belum ada rincian komoditas.</span>'}
  </div>`;
  marker.setPopupContent(popupContent);
}

function getCommodityType(type) {
  if (type === 'fish' || type === 'Hasil Tangkapan Ikan') return 'fish';
  if (type === 'leaf' || type === 'Hasil Pertanian') return 'agriculture';
  return null;
}

async function applyCommodityFilter() {
  activeCommodityMetric = selectedZoneTypes.size === 1 ? [...selectedZoneTypes][0] : 'all';
  const response = await fetch(`/api/dataset?commodity=${activeCommodityMetric}`, { cache: 'no-store' });
  const dataset = await response.json();
  if (!response.ok) {
    console.error(dataset.error || 'Dataset tidak dapat dimuat');
    return;
  }
  renderDataset(dataset);
  if (!zonesVisible) map.removeLayer(districtLayer);
}

function renderSummaryTable(districts) {
  summaryTitle.textContent = 'Ringkasan Produksi per Kecamatan';
  summaryReset.hidden = true;
  summaryHead.innerHTML = `
    <tr>
      <th>Kecamatan</th>
      <th>Produksi Ikan (Ton)</th>
      <th>Produksi Pertanian (Ton)</th>
      <th>Total Produksi</th>
      <th>Cluster</th>
    </tr>`;
  const tableBody = document.querySelector('.summary-table-wrap tbody');
  const rows = districts.map((district) => `
    <tr><td>${district.name}</td><td>${activeCommodityMetric === 'agriculture' ? '-' : district.production.ikan.toLocaleString('id-ID')}</td>
    <td>${activeCommodityMetric === 'fish' ? '-' : district.production.pertanian.toLocaleString('id-ID')}</td>
    <td>${(activeCommodityMetric === 'fish' ? district.production.ikan : activeCommodityMetric === 'agriculture' ? district.production.pertanian : district.production.total).toLocaleString('id-ID')}</td>
    <td><span class="cluster-badge ${district.cluster === 1 ? 'green' : district.cluster === 2 ? 'yellow' : 'red'}">${district.cluster}</span></td></tr>
  `).join('');
  tableBody.innerHTML = rows;
}

summaryReset.addEventListener('click', () => {
  renderSummaryTable(districtData);
});

fetch('/api/dataset', { cache: 'no-store' })
  .then((response) => response.json().then((data) => ({ ok: response.ok, data })))
  .then(({ ok, data }) => {
    if (!ok) throw new Error(data.error || 'Dataset tidak dapat dimuat');
    renderDataset(data);
  })
  .catch((error) => console.error(error));

const mapSection = document.querySelector('.map-section');
const infoCard = document.querySelector('.info-card');
const infoCardToggle = document.createElement('button');
infoCardToggle.type = 'button';
infoCardToggle.className = 'info-card-toggle';
infoCardToggle.textContent = ' Informasi Produksi ▸';
infoCardToggle.setAttribute('aria-label', ' informasi produksi');
infoCardToggle.hidden = true;
if (infoCard) {
  infoCard.parentNode.appendChild(infoCardToggle);
}

const titleLabel = document.createElement('div');
titleLabel.className = 'map-title-box';
titleLabel.innerHTML = `
  <div class="map-title-head">
    <span>Zona Kecamatan</span>
  </div>
  <div class="map-title-body">Data polygon dari MySQL</div>
`;
mapSection.appendChild(titleLabel);

const setInfoCardVisible = (visible) => {
  if (!infoCard) return;
  infoCard.classList.toggle('hidden', !visible);
  infoCardToggle.hidden = visible;
  infoCardToggle.textContent = visible ? 'Informasi Produksi ▾' : ' Informasi Produksi ▸';
  const closeButton = infoCard.querySelector('.close-btn');
  if (closeButton) closeButton.textContent = visible ? '▾' : '▸';
};

if (infoCard) {
  const closeButton = infoCard.querySelector('.close-btn');
  if (closeButton) closeButton.textContent = '▾';
  closeButton?.addEventListener('click', () => setInfoCardVisible(false));
  infoCardToggle.addEventListener('click', () => setInfoCardVisible(true));
}

const legend = L.control({ position: 'bottomright' });
legend.onAdd = function () {
  const div = L.DomUtil.create('div', 'info-box');
  const grades = [
    { label: 'Rendah', color: '#7cbc63' },
    { label: 'Sedang', color: '#f0d36d' },
    { label: 'Tinggi', color: '#ef6a5f' },
  ];

  div.innerHTML = '<strong>Produksi</strong><br>' + grades
    .map((item) => `<div><i style="display:inline-block;width:12px;height:12px;background:${item.color};margin-right:6px;border-radius:3px"></i>${item.label}</div>`)
    .join('<br>');

  return div;
};
legend.addTo(map);

const productionForm = document.getElementById('production-form');
if (productionForm) {
  productionForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    const message = document.getElementById('form-message');
    const response = await fetch('/api/production', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(Object.fromEntries(new FormData(productionForm))),
    });
    const result = await response.json();
    message.textContent = result.message || result.error;
    message.style.color = response.ok ? '#3d8a59' : '#b34235';
    if (response.ok) productionForm.reset();
  });
}

const verificationList = document.getElementById('verification-list');
async function loadVerificationList() {
  if (!verificationList) return;
  const response = await fetch('/api/production');
  const records = await response.json();
  const pending = records.filter((record) => record.status === 'pending');
  verificationList.innerHTML = pending.length ? pending.map((record) => `
    <div class="verification-item">
      <span><strong>${record.commodity}</strong> · ${record.production} ton · ${record.location}<br>
      <small>${record.creator_name} · ${record.type_name}</small></span>
      <span class="verification-actions">
        <button class="verify-btn" data-id="${record.id}" data-status="verified">Verifikasi</button>
        <button class="reject-btn" data-id="${record.id}" data-status="rejected">Tolak</button>
      </span>
    </div>
  `).join('') : '<p>Tidak ada data yang menunggu verifikasi.</p>';
  verificationList.querySelectorAll('button').forEach((button) => {
    button.addEventListener('click', async () => {
      await fetch(`/api/production/${button.dataset.id}/verify`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: button.dataset.status }),
      });
      loadVerificationList();
    });
  });
}
loadVerificationList();

const datasetPanel = document.getElementById('dataset-panel');
if (datasetPanel) {
  const datasetRole = datasetPanel.dataset.role;
  const isDatasetUser = datasetRole === 'user';
  const datasetDomain = document.getElementById('dataset-domain');
  const datasetTable = document.getElementById('dataset-table');
  const datasetDistrict = document.getElementById('dataset-district');
  const datasetDistrictField = document.getElementById('dataset-district-field');
  const datasetForm = document.getElementById('dataset-record-form');
  const datasetRecordId = document.getElementById('dataset-record-id');
  const datasetRecordList = document.getElementById('dataset-record-list');
  const datasetRequestList = document.getElementById('dataset-request-list');
  const datasetMessage = document.getElementById('dataset-form-message');
  const datasetSaveButton = document.getElementById('dataset-save-button');
  const datasetCancelEdit = document.getElementById('dataset-cancel-edit');
  const datasetDescription = document.getElementById('dataset-panel-description');
  const agricultureTables = [
    { value: 'crop_production', label: 'Pertanian per kecamatan', hasDistrict: true },
    { value: 'horticulture_production', label: 'Pertanian umum', hasDistrict: false },
  ];
  const fishTables = [
    { value: 'fish_production', label: 'Perikanan', hasDistrict: true },
  ];
  const districtNames = ['Pulau Ternate', 'Ternate Selatan', 'Ternate Tengah', 'Ternate Utara'];
  let datasetRecords = [];

  const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, (character) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
  })[character]);

  async function datasetFetch(url, options = {}) {
    const response = await fetch(url, options);
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Permintaan tidak berhasil');
    return result;
  }

  function tableDefinition(tableName) {
    return [...agricultureTables, ...fishTables].find((table) => table.value === tableName);
  }

  function resetDatasetForm() {
    datasetForm.reset();
    datasetRecordId.value = '';
    document.getElementById('dataset-year').value = new Date().getFullYear();
    datasetDistrict.selectedIndex = 0;
    datasetSaveButton.textContent = isDatasetUser ? 'Ajukan penambahan' : 'Tambah data';
    datasetCancelEdit.hidden = true;
    syncDatasetTableFields();
  }

  function populateDatasetTables() {
    const tables = datasetDomain.value === 'fish' ? fishTables : agricultureTables;
    datasetTable.innerHTML = tables.map((table) =>
      `<option value="${table.value}">${table.label}</option>`
    ).join('');
    syncDatasetTableFields();
  }

  function populateDatasetDistricts(selectedDistrict = '') {
    datasetDistrict.innerHTML = '<option value="">Pilih kecamatan</option>' + districtNames
      .map((name) => `<option value="${escapeHtml(name)}">${escapeHtml(name)}</option>`)
      .join('');
    if (selectedDistrict) datasetDistrict.value = selectedDistrict;
  }

  function syncDatasetTableFields() {
    const definition = tableDefinition(datasetTable.value);
    const hasDistrict = Boolean(definition?.hasDistrict);
    datasetDistrictField.hidden = !hasDistrict;
    datasetDistrict.required = hasDistrict;
    if (!hasDistrict) datasetDistrict.value = '';
  }

  function formatRequestPayload(requestRecord) {
    const values = requestRecord.operation === 'delete'
      ? requestRecord.original_data
      : requestRecord.payload;
    if (!values) return '';
    const parts = [values.commodity, values.district_name, values.year, values.production_ton]
      .filter((value) => value !== undefined && value !== null && value !== '');
    return parts.map(escapeHtml).join(' · ');
  }

  function renderDatasetRequests(requests) {
    if (!requests.length) {
      datasetRequestList.innerHTML = '<p>Tidak ada permintaan dataset.</p>';
      return;
    }
    datasetRequestList.innerHTML = requests.map((item) => {
      const operationLabels = { create: 'Tambah', update: 'Edit', delete: 'Hapus' };
      const statusLabels = { pending: 'Menunggu verifikasi', approved: 'Disetujui', rejected: 'Ditolak' };
      const actions = isDatasetUser ? '' : `
        <span class="verification-actions">
          <button class="verify-btn" type="button" data-request-id="${item.id}" data-decision="approved">Setujui</button>
          <button class="reject-btn" type="button" data-request-id="${item.id}" data-decision="rejected">Tolak</button>
        </span>`;
      return `
        <div class="verification-item dataset-request-item">
          <span><strong>${operationLabels[item.operation]} · ${escapeHtml(item.table_name)}</strong> · ${formatRequestPayload(item)}<br>
          <small>${escapeHtml(item.creator_name || 'Anda')} · ${statusLabels[item.status]}</small></span>
          ${actions}
        </div>`;
    }).join('');
  }

  async function loadDatasetRequests() {
    try {
      const result = await datasetFetch(`/api/commodity-requests?domain=${datasetDomain.value}`);
      renderDatasetRequests(result);
    } catch (error) {
      datasetRequestList.textContent = error.message;
    }
  }

  async function loadDatasetRecords() {
    datasetRecordList.textContent = 'Memuat data...';
    try {
      const result = await datasetFetch(`/api/commodity-data?domain=${datasetDomain.value}`);
      datasetRecords = result.records;
      renderDatasetRecords();
    } catch (error) {
      datasetRecordList.textContent = error.message;
    }
  }

  function renderDatasetRecords() {
    if (!datasetRecords.length) {
      datasetRecordList.innerHTML = '<p>Belum ada data pada bidang ini.</p>';
      return;
    }
    const rows = datasetRecords.map((record) => `
      <tr>
        <td>${escapeHtml(record.district_name || '-')}</td>
        <td>${escapeHtml(record.commodity)}</td>
        <td>${record.year}</td>
        <td>${Number(record.production_ton).toLocaleString('id-ID')}</td>
        <td class="dataset-row-actions">
          <button class="edit-dataset-btn" type="button" data-table="${record.table_name}" data-record-id="${record.id}">${isDatasetUser ? 'Ajukan edit' : 'Edit'}</button>
          <button class="delete-dataset-btn" type="button" data-table="${record.table_name}" data-record-id="${record.id}">${isDatasetUser ? 'Ajukan hapus' : 'Hapus'}</button>
        </td>
      </tr>`).join('');
    datasetRecordList.innerHTML = `
      <div class="dataset-table-scroll">
        <table class="dataset-table">
          <thead><tr><th>Kecamatan</th><th>Komoditas</th><th>Tahun</th><th>Produksi (ton)</th><th>Aksi</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>`;
  }

  function editDatasetRecord(tableName, recordId) {
    const record = datasetRecords.find((item) =>
      item.table_name === tableName && item.id === Number(recordId)
    );
    if (!record) return;
    datasetTable.value = tableName;
    syncDatasetTableFields();
    datasetRecordId.value = record.id;
    datasetDistrict.value = record.district_name || '';
    document.getElementById('dataset-commodity').value = record.commodity;
    document.getElementById('dataset-year').value = record.year;
    document.getElementById('dataset-production').value = record.production_ton;
    datasetSaveButton.textContent = isDatasetUser ? 'Ajukan perubahan' : 'Simpan perubahan';
    datasetCancelEdit.hidden = false;
    datasetMessage.textContent = '';
    datasetForm.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }

  async function requestDatasetChange(operation, tableName, recordId = null, entry = null) {
    return datasetFetch('/api/commodity-requests', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        domain: datasetDomain.value,
        table_name: tableName,
        operation,
        record_id: recordId,
        data: entry,
      }),
    });
  }

  datasetForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    const entry = Object.fromEntries(new FormData(datasetForm));
    const tableName = datasetTable.value;
    const recordId = datasetRecordId.value;
    const operation = recordId ? 'update' : 'create';
    let result;
    try {
      if (isDatasetUser) {
        result = await requestDatasetChange(operation, tableName, recordId || null, entry);
      } else if (recordId) {
        result = await datasetFetch(`/api/commodity-data/${tableName}/${recordId}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ ...entry, domain: datasetDomain.value }),
        });
      } else {
        result = await datasetFetch('/api/commodity-data', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ ...entry, domain: datasetDomain.value, table_name: tableName }),
        });
      }
      datasetMessage.textContent = result.message;
      datasetMessage.style.color = '#3d8a59';
      resetDatasetForm();
      await loadDatasetRecords();
      await loadDatasetRequests();
    } catch (error) {
      datasetMessage.textContent = error.message;
      datasetMessage.style.color = '#b34235';
    }
  });

  datasetRecordList.addEventListener('click', async (event) => {
    const button = event.target.closest('button[data-record-id]');
    if (!button) return;
    const { table, recordId } = button.dataset;
    if (button.classList.contains('edit-dataset-btn')) {
      editDatasetRecord(table, recordId);
      return;
    }
    if (!window.confirm(isDatasetUser ? 'Ajukan penghapusan data ini?' : 'Hapus data ini?')) return;
    try {
      const result = isDatasetUser
        ? await requestDatasetChange('delete', table, recordId)
        : await datasetFetch(`/api/commodity-data/${table}/${recordId}`, {
          method: 'DELETE',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ domain: datasetDomain.value }),
        });
      datasetMessage.textContent = result.message;
      datasetMessage.style.color = '#3d8a59';
      await loadDatasetRecords();
      await loadDatasetRequests();
    } catch (error) {
      datasetMessage.textContent = error.message;
      datasetMessage.style.color = '#b34235';
    }
  });

  datasetRequestList.addEventListener('click', async (event) => {
    const button = event.target.closest('button[data-request-id]');
    if (!button) return;
    try {
      const result = await datasetFetch(`/api/commodity-requests/${button.dataset.requestId}/review`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: button.dataset.decision }),
      });
      datasetMessage.textContent = result.message;
      datasetMessage.style.color = '#3d8a59';
      await loadDatasetRecords();
      await loadDatasetRequests();
    } catch (error) {
      datasetMessage.textContent = error.message;
      datasetMessage.style.color = '#b34235';
    }
  });

  datasetDomain.addEventListener('change', () => {
    resetDatasetForm();
    populateDatasetTables();
    loadDatasetRecords();
    loadDatasetRequests();
  });
  datasetTable.addEventListener('change', syncDatasetTableFields);
  datasetCancelEdit.addEventListener('click', resetDatasetForm);
  datasetDomain.value = datasetRole === 'admin_perikanan' ? 'fish' : 'agriculture';
  populateDatasetDistricts();
  populateDatasetTables();
  resetDatasetForm();
  datasetDescription.textContent = isDatasetUser
    ? 'Tambah, edit, dan hapus akan menunggu persetujuan admin bidang terkait.'
    : 'Perubahan langsung berlaku. Permintaan user hanya menampilkan bidang admin ini.';
  loadDatasetRecords();
  loadDatasetRequests();
}

const layerDialog = document.getElementById('layer-dialog');
const aboutDialog = document.getElementById('about-dialog');

document.getElementById('layer-toggle').addEventListener('click', () => {
  layerDialog.hidden = !layerDialog.hidden;
  aboutDialog.hidden = true;
});

document.getElementById('about-toggle').addEventListener('click', () => {
  aboutDialog.hidden = !aboutDialog.hidden;
  layerDialog.hidden = true;
});

document.querySelectorAll('[data-close-dialog]').forEach((button) => {
  button.addEventListener('click', () => {
    document.getElementById(button.dataset.closeDialog).hidden = true;
  });
});

document.getElementById('layer-zones').addEventListener('change', (event) => {
  zonesVisible = event.target.checked;
  if (zonesVisible) {
    map.addLayer(districtLayer);
    applyCommodityFilter();
  }
  else map.removeLayer(districtLayer);
});

document.getElementById('layer-markers').addEventListener('change', (event) => {
  if (event.target.checked) map.addLayer(markerLayer);
  else map.removeLayer(markerLayer);
});

document.getElementById('layer-labels').addEventListener('change', (event) => {
  locationLabelsVisible = event.target.checked;
  locationMarkers.forEach((marker) => {
    if (locationLabelsVisible) marker.openTooltip();
    else marker.closeTooltip();
  });
});

document.querySelectorAll('input[name="zone-filter"]').forEach((input) => {
  input.addEventListener('change', (event) => {
    if (event.target.checked) selectedZoneTypes.add(event.target.value);
    else selectedZoneTypes.delete(event.target.value);
    if (selectedZoneTypes.size === 0) {
      selectedZoneTypes.add('fish');
      event.target.checked = true;
    }
    applyCommodityFilter();
  });
});

document.querySelectorAll('input[name="basemap"]').forEach((input) => {
  input.addEventListener('change', (event) => {
    if (event.target.value === 'satellite') {
      map.removeLayer(streetLayer);
      satelliteLayer.addTo(map);
    } else {
      map.removeLayer(satelliteLayer);
      streetLayer.addTo(map);
    }
  });
});
