IF NOT EXISTS (SELECT name FROM sys.databases WHERE name = N'dashboard_data')
BEGIN
    CREATE DATABASE [dashboard_data];
END
GO

USE [dashboard_data];
GO

-- ==========================================================
-- 1. TABLA: amano_europa_tickets
-- ==========================================================
IF OBJECT_ID('dbo.amano_europa_tickets', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.amano_europa_tickets (
        id BIGINT IDENTITY(1,1) PRIMARY KEY,
        sede VARCHAR(30) NOT NULL,
        ticket VARCHAR(50) NULL,
        contrato NVARCHAR(100) NULL,
        perfil_acceso NVARCHAR(100) NULL,
        tipo_tarjeta NVARCHAR(100) NULL,
        producto NVARCHAR(100) NULL,
        entrada NVARCHAR(100) NULL,
        hora_entrada DATETIME2(0) NULL,
        matricula VARCHAR(30) NULL,
        salida NVARCHAR(100) NULL,
        hora_salida DATETIME2(0) NULL,
        cajero_automatico NVARCHAR(100) NULL,
        hora_pago DATETIME2(0) NULL,
        importe_pagar DECIMAL(12, 2) NULL,
        duracion VARCHAR(30) NULL,
        eventos NVARCHAR(255) NULL,
        numero_tarjeta VARCHAR(100) NULL,
        nombre NVARCHAR(100) NULL,
        apellido NVARCHAR(100) NULL,
        fecha_carga DATETIME2(0) NOT NULL DEFAULT SYSDATETIME()
    );

    CREATE INDEX IX_ae_tickets_sede_entrada ON dbo.amano_europa_tickets (sede, hora_entrada);
    CREATE INDEX IX_ae_tickets_ticket ON dbo.amano_europa_tickets (ticket);
END
GO

-- ==========================================================
-- 2. TABLA: amano_europa_ventas
-- ==========================================================
IF OBJECT_ID('dbo.amano_europa_ventas', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.amano_europa_ventas (
        id BIGINT IDENTITY(1,1) PRIMARY KEY,
        sede VARCHAR(30) NOT NULL,
        fecha_pago DATETIME2(0) NULL,
        dispositivo NVARCHAR(100) NULL,
        tipo_venta NVARCHAR(100) NULL,
        hora_entrada DATETIME2(0) NULL,
        hora_salida DATETIME2(0) NULL,
        tarifa DECIMAL(12, 2) NULL,
        descuento_monto DECIMAL(12, 2) NULL,
        importe_total DECIMAL(12, 2) NULL,
        pagado DECIMAL(12, 2) NULL,
        vuelto DECIMAL(12, 2) NULL,
        pagado_neto_cambio DECIMAL(12, 2) NULL,
        valor_iva DECIMAL(12, 2) NULL,
        neto DECIMAL(12, 2) NULL,
        tipo_pago NVARCHAR(100) NULL,
        subtipo_pago NVARCHAR(100) NULL,
        observaciones NVARCHAR(255) NULL,
        numero_tarjeta VARCHAR(100) NULL,
        transbank VARCHAR(100) NULL,
        codigo_mantenimiento VARCHAR(50) NULL,
        usuario NVARCHAR(100) NULL,
        turno VARCHAR(50) NULL,
        numero_recibo VARCHAR(50) NULL,
        recibo_fiscal VARCHAR(50) NULL,
        ticket VARCHAR(50) NULL,
        nombre_conductor NVARCHAR(100) NULL,
        matricula VARCHAR(30) NULL,
        producto NVARCHAR(100) NULL,
        articulo NVARCHAR(100) NULL,
        tipo_tarjeta NVARCHAR(100) NULL,
        perfil_acceso NVARCHAR(100) NULL,
        descuento_nombre NVARCHAR(150) NULL,
        tienda_numero VARCHAR(50) NULL,
        descuento_numero VARCHAR(50) NULL,
        fecha_carga DATETIME2(0) NOT NULL DEFAULT SYSDATETIME()
    );

    CREATE INDEX IX_ae_ventas_sede_fecha ON dbo.amano_europa_ventas (sede, fecha_pago);
    CREATE INDEX IX_ae_ventas_ticket ON dbo.amano_europa_ventas (ticket);
END
GO

-- ==========================================================
-- 3. TABLA: amano_europa_descuentos
-- ==========================================================
IF OBJECT_ID('dbo.amano_europa_descuentos', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.amano_europa_descuentos (
        id BIGINT IDENTITY(1,1) PRIMARY KEY,
        sede VARCHAR(30) NOT NULL,
        hora_pago DATETIME2(0) NULL,
        dispositivo NVARCHAR(100) NULL,
        cliente NVARCHAR(100) NULL,
        contrato NVARCHAR(100) NULL,
        descuento NVARCHAR(150) NULL,
        tipo_valor VARCHAR(30) NULL,
        importe DECIMAL(12, 2) NULL,
        codigo_descuento VARCHAR(50) NULL,
        tienda_numero VARCHAR(50) NULL,
        descuento_numero VARCHAR(50) NULL,
        numero_recibo VARCHAR(50) NULL,
        ticket VARCHAR(50) NULL,
        entrada NVARCHAR(100) NULL,
        hora_entrada DATETIME2(0) NULL,
        matricula VARCHAR(30) NULL,
        perfil_acceso NVARCHAR(100) NULL,
        tipo_tarjeta NVARCHAR(100) NULL,
        producto NVARCHAR(100) NULL,
        fecha_carga DATETIME2(0) NOT NULL DEFAULT SYSDATETIME()
    );

    CREATE INDEX IX_ae_descuentos_sede_pago ON dbo.amano_europa_descuentos (sede, hora_pago);
    CREATE INDEX IX_ae_descuentos_ticket ON dbo.amano_europa_descuentos (ticket);
END
GO