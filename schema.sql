CREATE DATABASE IF NOT EXISTS gis_ternate CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE gis_ternate;

-- Setelah import schema, jalankan: python import_public_boundaries.py
-- Script tersebut memasang batas kecamatan dari ADMINISTRASI_AR_50K.shp.
-- Batas pada ZIP ini menjadi sumber utama geometri zona aplikasi.

CREATE TABLE IF NOT EXISTS districts (
  id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(100) NOT NULL,
  value INT NOT NULL,
  cluster TINYINT NOT NULL,
  coords JSON NOT NULL,
  production_ikan DECIMAL(12,2) NOT NULL,
  production_pertanian DECIMAL(12,2) NOT NULL,
  production_total DECIMAL(12,2) NOT NULL,
  commodity VARCHAR(150) NOT NULL,
  type_name VARCHAR(100) NOT NULL
);

CREATE TABLE IF NOT EXISTS production_markers (
  id INT AUTO_INCREMENT PRIMARY KEY,
  label VARCHAR(100) NOT NULL,
  value VARCHAR(50) NOT NULL,
  type_name VARCHAR(20) NOT NULL,
  emoji VARCHAR(10) NOT NULL,
  latitude DECIMAL(10,6) NOT NULL,
  longitude DECIMAL(10,6) NOT NULL,
  district_name VARCHAR(100) NOT NULL
);

ALTER TABLE production_markers ADD COLUMN IF NOT EXISTS district_name VARCHAR(100) NOT NULL DEFAULT 'Belum ditentukan';

CREATE TABLE IF NOT EXISTS users (
  id INT AUTO_INCREMENT PRIMARY KEY,
  username VARCHAR(60) NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL,
  full_name VARCHAR(120) NOT NULL,
  role ENUM('admin_pertanian', 'admin_perikanan', 'user') NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS production_records (
  id INT AUTO_INCREMENT PRIMARY KEY,
  commodity VARCHAR(150) NOT NULL,
  production DECIMAL(12,2) NOT NULL,
  type_name VARCHAR(100) NOT NULL,
  latitude DECIMAL(10,6) NOT NULL,
  longitude DECIMAL(10,6) NOT NULL,
  location VARCHAR(255) NOT NULL,
  status ENUM('pending', 'verified', 'rejected') NOT NULL DEFAULT 'pending',
  created_by INT NOT NULL,
  verified_by INT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_production_creator FOREIGN KEY (created_by) REFERENCES users(id),
  CONSTRAINT fk_production_verifier FOREIGN KEY (verified_by) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS crop_production (
  id INT AUTO_INCREMENT PRIMARY KEY,
  district_name VARCHAR(100) NOT NULL,
  commodity VARCHAR(150) NOT NULL,
  year SMALLINT NOT NULL,
  production_ton DECIMAL(12,3) NOT NULL,
  source_file VARCHAR(255) NOT NULL,
  UNIQUE KEY crop_record (district_name, commodity, year)
);

CREATE TABLE IF NOT EXISTS horticulture_production (
  id INT AUTO_INCREMENT PRIMARY KEY,
  commodity VARCHAR(150) NOT NULL,
  year SMALLINT NOT NULL,
  production_ton DECIMAL(12,3) NOT NULL,
  source_file VARCHAR(255) NOT NULL,
  UNIQUE KEY horticulture_record (commodity, year)
);

CREATE TABLE IF NOT EXISTS fish_production (
  id INT AUTO_INCREMENT PRIMARY KEY,
  district_name VARCHAR(100) NOT NULL,
  commodity VARCHAR(150) NOT NULL,
  year SMALLINT NOT NULL,
  production_ton DECIMAL(12,3) NOT NULL,
  source_file VARCHAR(255) NOT NULL,
  UNIQUE KEY fish_record (district_name, commodity, year)
);

-- Hapus marker perikanan yang tidak lagi digunakan sebelum seed marker dijalankan.
DELETE FROM production_markers
WHERE label IN ('Perikanan Bastiong', 'Perikanan Jambula');

INSERT IGNORE INTO users (username, password_hash, full_name, role) VALUES
('admin_pertanian', 'scrypt:32768:8:1$ADfdMuDMVLa5ghSZ$ed2fb074898cf9e015cc5f8b8dd5432494bfcebe7642e24483dd52b930bfd44a182f0f3b64559929d021cd474e4a8497bac2bf19e4dfec150a867ba67f2e6727', 'Admin Dinas Pertanian', 'admin_pertanian'),
('admin_perikanan', 'scrypt:32768:8:1$oRPRvBMXYyeKS2cr$8b7aa146d42dbf252231915535afa443bf7db0052ac27ecc609b11feeedb9e9a0601f2ed5d5c4be3a563e3249dbc192fe6f9b7d593d197929b80b9ac4584e74a', 'Admin Dinas Perikanan', 'admin_perikanan'),
('user', 'scrypt:32768:8:1$Lm7SU8PUcCTb5IsE$040ca003eac9482dbce3ab0afa8b8c5fb9010f7417e18011a2265e155b14792a2ed2ecf130853f914f71a59ff22b4c9fdc0dba813211f7c576d4fb0a9f58c1b5', 'Pengguna Usaha', 'user');

INSERT INTO districts (name, value, cluster, coords, production_ikan, production_pertanian, production_total, commodity, type_name) VALUES
('Ternate Selatan', 77, '1', '[]', 0, 28.08, 28.08, 'Tanaman pangan 2025', 'Hasil Pertanian'),
('Ternate Utara', 92, '3', '[]', 2902.93, 6.62, 2909.55, 'Tanaman pangan 2025', 'Hasil Pertanian'),
('Ternate Tengah', 77, '2', '[]', 0, 19.48, 19.48, 'Tanaman pangan 2025', 'Hasil Pertanian'),
('Pulau Ternate', 78, '2', '[]', 0, 7.96, 7.96, 'Tanaman pangan 2025', 'Hasil Pertanian');

INSERT INTO production_markers (label, value, type_name, emoji, latitude, longitude, district_name) VALUES
('Tebar Takome', 'Lokasi pertanian', 'leaf', '🌿', 0.849538, 127.319484, 'Pulau Ternate'),
('Perikanan Dufa-Dufa', 'Lokasi perikanan', 'fish', '🐟', 0.814337, 127.388672, 'Ternate Utara'),
('Tesel Sasa', 'Lokasi pertanian', 'leaf', '🌿', 0.756463, 127.327859, 'Ternate Selatan'),
('Ternate Tengah Marikurubu', 'Lokasi pertanian', 'leaf', '🌿', 0.789113, 127.370891, 'Ternate Tengah'),
('Tubo 1', 'Lokasi pertanian', 'leaf', '🌿', 0.824038, 127.376984, 'Ternate Utara');

-- Sinkronkan marker jika database sudah pernah dibuat sebelum koordinat diperbarui.
UPDATE production_markers SET latitude = 0.849538, longitude = 127.319484, value = 'Lokasi pertanian', type_name = 'leaf', emoji = '🌿', district_name = 'Pulau Ternate' WHERE label = 'Tebar Takome';
UPDATE production_markers SET latitude = 0.814337, longitude = 127.388672, value = 'Lokasi perikanan', type_name = 'fish', emoji = '🐟', district_name = 'Ternate Utara' WHERE label = 'Perikanan Dufa-Dufa';
UPDATE production_markers SET latitude = 0.756463, longitude = 127.327859, value = 'Lokasi pertanian', type_name = 'leaf', emoji = '🌿', district_name = 'Ternate Selatan' WHERE label = 'Tesel Sasa';
UPDATE production_markers SET latitude = 0.789113, longitude = 127.370891, value = 'Lokasi pertanian', type_name = 'leaf', emoji = '🌿', district_name = 'Ternate Tengah' WHERE label = 'Ternate Tengah Marikurubu';
UPDATE production_markers SET latitude = 0.824038, longitude = 127.376984, value = 'Lokasi pertanian', type_name = 'leaf', emoji = '🌿', district_name = 'Ternate Utara' WHERE label = 'Tubo 1';