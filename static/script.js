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
  populateMarkerSelect(dataset.markers);
  const zoneBounds = L.featureGroup();
  if (!markersRendered) {
    dataset.markers.forEach((point) => {
      const marker = L.marker(point.coords, { icon: createMarkerIcon(point.emoji, point.type_name) }).addTo(markerLayer);
      if (point.id !== undefined) marker.on('click', () => selectMarker(point.id));
      marker.bindPopup(`<div class="custom-popup"><strong>${point.label}</strong>Kecamatan: ${point.district_name}<br>Produksi: ${point.value}</div>`);
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
    const production = district.production;
    document.getElementById('info-kecamatan').textContent = ': ' + district.name;
    document.getElementById('info-komoditas').textContent = ': ' + district.commodity;
    document.getElementById('info-jenis').textContent = ': ' + district.type_name;
    document.getElementById('info-produksi').textContent = ': ' + production.total.toLocaleString('id-ID') + ' Ton/Tahun';
    document.getElementById('info-cluster').textContent = ': ' + clusterLabels[district.cluster];
  });
  });
  if (zoneBounds.getLayers().length) {
    map.fitBounds(zoneBounds.getBounds().pad(0.08));
    setTimeout(() => map.invalidateSize(), 80);
  }
  renderSummaryTable(districtData);
}

function bindDistrictPopup(district, polygon) {
  const production = activeCommodityMetric === 'fish'
    ? district.production.ikan
    : activeCommodityMetric === 'agriculture'
      ? district.production.pertanian
      : district.production.total;
  const label = activeCommodityMetric === 'fish' ? 'Produksi Perikanan' : activeCommodityMetric === 'agriculture' ? 'Produksi Pertanian' : 'Total Produksi';
  polygon.bindPopup(`<div class="custom-popup"><strong>${district.name}</strong>${label}: ${production.toLocaleString('id-ID')} ton<br>${clusterLabels[district.cluster]}</div>`);
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
  const tableBody = document.querySelector('.summary-table-wrap tbody');
  const rows = districts.map((district) => `
    <tr><td>${district.name}</td><td>${activeCommodityMetric === 'agriculture' ? '-' : district.production.ikan.toLocaleString('id-ID')}</td>
    <td>${activeCommodityMetric === 'fish' ? '-' : district.production.pertanian.toLocaleString('id-ID')}</td>
    <td>${(activeCommodityMetric === 'fish' ? district.production.ikan : activeCommodityMetric === 'agriculture' ? district.production.pertanian : district.production.total).toLocaleString('id-ID')}</td>
    <td><span class="cluster-badge ${district.cluster === 1 ? 'green' : district.cluster === 2 ? 'yellow' : 'red'}">${district.cluster}</span></td></tr>
  `).join('');
  tableBody.innerHTML = rows;
}

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

const target = document.getElementById('info-kecamatan');
if (target) {
  target.textContent = ': Ternate Utara';
}

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
