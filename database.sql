
-- ==========================================
-- 1. MEMBUAT DATABASE
-- ==========================================

CREATE DATABASE IF NOT EXISTS db_kk;

USE db_kk;

-- ==========================================
-- 2. TABEL IDENTITAS KARTU KELUARGA
-- ==========================================

CREATE TABLE IF NOT EXISTS tbl_identitasKK (

    id_kk INT AUTO_INCREMENT PRIMARY KEY,

    no_kk VARCHAR(30) NOT NULL UNIQUE,

    kepala_keluarga VARCHAR(100) NOT NULL,

    alamat TEXT,

    rt VARCHAR(5),

    rw VARCHAR(5),

    desa_kelurahan VARCHAR(100),

    kecamatan VARCHAR(100),

    kabupaten_kota VARCHAR(100),

    provinsi VARCHAR(100),

    kode_pos VARCHAR(10),

    tanggal_dikeluarkan DATE,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP

) ENGINE=InnoDB;

-- ==========================================
-- 3. TABEL ANGGOTA KELUARGA
-- ==========================================

CREATE TABLE IF NOT EXISTS tbl_anggotaKeluargaKK (

    id_anggota INT AUTO_INCREMENT PRIMARY KEY,

    id_kk INT NOT NULL,

    nama_lengkap VARCHAR(100) NOT NULL,

    nik VARCHAR(30),

    jenis_kelamin VARCHAR(20),

    tempat_lahir VARCHAR(100),

    tanggal_lahir DATE,

    agama VARCHAR(30),

    pendidikan VARCHAR(100),

    jenis_pekerjaan VARCHAR(100),

    golongan_darah VARCHAR(10),

    status_perkawinan VARCHAR(50),

    tanggal_perkawinan DATE,

    status_hubungan VARCHAR(50),

    kewarganegaraan VARCHAR(10),

    no_paspor VARCHAR(30),

    no_kitap VARCHAR(30),

    nama_ayah VARCHAR(100),

    nama_ibu VARCHAR(100),

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,

    CONSTRAINT fk_anggota_kk

        FOREIGN KEY (id_kk)

        REFERENCES tbl_identitasKK(id_kk)

        ON DELETE CASCADE

        ON UPDATE CASCADE

) ENGINE=InnoDB;