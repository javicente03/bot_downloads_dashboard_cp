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
        id                  BIGINT IDENTITY(1,1) PRIMARY KEY,
        sede                VARCHAR(30)     NOT NULL,
        fecha_reporte       DATE            NOT NULL,
        ticket              VARCHAR(50)     NULL,
        contrato            NVARCHAR(100)   NULL,
        perfil_acceso       NVARCHAR(100)   NULL,
        tipo_tarjeta        NVARCHAR(100)   NULL,
        producto            NVARCHAR(100)   NULL,
        entrada             NVARCHAR(100)   NULL,
        hora_entrada        DATETIME2(0)    NULL,
        matricula           VARCHAR(30)     NULL,
        salida              NVARCHAR(100)   NULL,
        hora_salida         DATETIME2(0)    NULL,
        cajero_automatico   NVARCHAR(100)   NULL,
        hora_pago           DATETIME2(0)    NULL,
        importe_pagar       DECIMAL(12, 2)  NULL,
        duracion            VARCHAR(30)     NULL,
        eventos             NVARCHAR(255)   NULL,
        numero_tarjeta      VARCHAR(100)    NULL,
        nombre              NVARCHAR(100)   NULL,
        apellido            NVARCHAR(100)   NULL,
        fecha_carga         DATETIME2(0)    NOT NULL DEFAULT SYSDATETIME()
    );

    CREATE INDEX IX_ae_tickets_sede_fecha ON dbo.amano_europa_tickets (sede, fecha_reporte);
    CREATE INDEX IX_ae_tickets_ticket ON dbo.amano_europa_tickets (ticket);
END
ELSE IF COL_LENGTH('dbo.amano_europa_tickets', 'fecha_reporte') IS NULL
BEGIN
    ALTER TABLE dbo.amano_europa_tickets ADD fecha_reporte DATE NULL;
    EXEC('UPDATE dbo.amano_europa_tickets SET fecha_reporte = COALESCE(CAST(hora_entrada AS DATE), CAST(fecha_carga AS DATE)) WHERE fecha_reporte IS NULL;');
    ALTER TABLE dbo.amano_europa_tickets ALTER COLUMN fecha_reporte DATE NOT NULL;
    DROP INDEX IF EXISTS IX_ae_tickets_sede_entrada ON dbo.amano_europa_tickets;
    CREATE INDEX IX_ae_tickets_sede_fecha ON dbo.amano_europa_tickets (sede, fecha_reporte);
END
GO

-- ==========================================================
-- 2. TABLA: amano_europa_ventas
-- ==========================================================
IF OBJECT_ID('dbo.amano_europa_ventas', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.amano_europa_ventas (
        id                      BIGINT IDENTITY(1,1) PRIMARY KEY,
        sede                    VARCHAR(30)     NOT NULL,
        fecha_reporte           DATE            NOT NULL,
        fecha_pago              DATETIME2(0)    NULL,
        dispositivo             NVARCHAR(100)   NULL,
        tipo_venta              NVARCHAR(100)   NULL,
        hora_entrada            DATETIME2(0)    NULL,
        hora_salida             DATETIME2(0)    NULL,
        tarifa                  DECIMAL(12, 2)  NULL,
        descuento_monto         DECIMAL(12, 2)  NULL,
        importe_total           DECIMAL(12, 2)  NULL,
        pagado                  DECIMAL(12, 2)  NULL,
        vuelto                  DECIMAL(12, 2)  NULL,
        pagado_neto_cambio      DECIMAL(12, 2)  NULL,
        valor_iva               DECIMAL(12, 2)  NULL,
        neto                    DECIMAL(12, 2)  NULL,
        tipo_pago               NVARCHAR(100)   NULL,
        subtipo_pago            NVARCHAR(100)   NULL,
        observaciones           NVARCHAR(255)   NULL,
        numero_tarjeta          VARCHAR(100)    NULL,
        transbank               NVARCHAR(100)   NULL,
        codigo_mantenimiento    VARCHAR(50)     NULL,
        usuario                 NVARCHAR(100)   NULL,
        turno                   VARCHAR(50)     NULL,
        numero_recibo           VARCHAR(50)     NULL,
        recibo_fiscal           VARCHAR(50)     NULL,
        ticket                  VARCHAR(50)     NULL,
        nombre_conductor        NVARCHAR(100)   NULL,
        matricula               VARCHAR(30)     NULL,
        producto                NVARCHAR(100)   NULL,
        articulo                NVARCHAR(100)   NULL,
        tipo_tarjeta            NVARCHAR(100)   NULL,
        perfil_acceso           NVARCHAR(100)   NULL,
        descuento_nombre        NVARCHAR(150)   NULL,
        tienda_numero           VARCHAR(50)     NULL,
        descuento_numero        VARCHAR(50)     NULL,
        fecha_carga             DATETIME2(0)    NOT NULL DEFAULT SYSDATETIME()
    );

    CREATE INDEX IX_ae_ventas_sede_fecha ON dbo.amano_europa_ventas (sede, fecha_reporte);
    CREATE INDEX IX_ae_ventas_ticket ON dbo.amano_europa_ventas (ticket);
END
ELSE IF COL_LENGTH('dbo.amano_europa_ventas', 'fecha_reporte') IS NULL
BEGIN
    ALTER TABLE dbo.amano_europa_ventas ADD fecha_reporte DATE NULL;
    EXEC('UPDATE dbo.amano_europa_ventas SET fecha_reporte = COALESCE(CAST(fecha_pago AS DATE), CAST(fecha_carga AS DATE)) WHERE fecha_reporte IS NULL;');
    ALTER TABLE dbo.amano_europa_ventas ALTER COLUMN fecha_reporte DATE NOT NULL;
    DROP INDEX IF EXISTS IX_ae_ventas_sede_fecha ON dbo.amano_europa_ventas;
    CREATE INDEX IX_ae_ventas_sede_fecha ON dbo.amano_europa_ventas (sede, fecha_reporte);
END
GO

-- ==========================================================
-- 3. TABLA: amano_europa_descuentos
-- ==========================================================
IF OBJECT_ID('dbo.amano_europa_descuentos', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.amano_europa_descuentos (
        id                  BIGINT IDENTITY(1,1) PRIMARY KEY,
        sede                VARCHAR(30)     NOT NULL,
        fecha_reporte       DATE            NOT NULL,
        hora_pago           DATETIME2(0)    NULL,
        dispositivo         NVARCHAR(100)   NULL,
        cliente             NVARCHAR(100)   NULL,
        contrato            NVARCHAR(100)   NULL,
        descuento           NVARCHAR(150)   NULL,
        tipo_valor          VARCHAR(30)     NULL,
        importe             DECIMAL(12, 2)  NULL,
        codigo_descuento    VARCHAR(50)     NULL,
        tienda_numero       VARCHAR(50)     NULL,
        descuento_numero    VARCHAR(50)     NULL,
        numero_recibo       VARCHAR(50)     NULL,
        ticket              VARCHAR(50)     NULL,
        entrada             NVARCHAR(100)   NULL,
        hora_entrada        DATETIME2(0)    NULL,
        matricula           VARCHAR(30)     NULL,
        perfil_acceso       NVARCHAR(100)   NULL,
        tipo_tarjeta        NVARCHAR(100)   NULL,
        producto            NVARCHAR(100)   NULL,
        fecha_carga         DATETIME2(0)    NOT NULL DEFAULT SYSDATETIME()
    );

    CREATE INDEX IX_ae_descuentos_sede_fecha ON dbo.amano_europa_descuentos (sede, fecha_reporte);
    CREATE INDEX IX_ae_descuentos_ticket ON dbo.amano_europa_descuentos (ticket);
END
ELSE IF COL_LENGTH('dbo.amano_europa_descuentos', 'fecha_reporte') IS NULL
BEGIN
    ALTER TABLE dbo.amano_europa_descuentos ADD fecha_reporte DATE NULL;
    EXEC('UPDATE dbo.amano_europa_descuentos SET fecha_reporte = COALESCE(CAST(hora_pago AS DATE), CAST(fecha_carga AS DATE)) WHERE fecha_reporte IS NULL;');
    ALTER TABLE dbo.amano_europa_descuentos ALTER COLUMN fecha_reporte DATE NOT NULL;
    DROP INDEX IF EXISTS IX_ae_descuentos_sede_pago ON dbo.amano_europa_descuentos;
    CREATE INDEX IX_ae_descuentos_sede_fecha ON dbo.amano_europa_descuentos (sede, fecha_reporte);
END
GO

-- ============================================================================
-- 4. TABLA: AMANO JAPAN TRANSACTIONS (Unificada 43 y 44 columnas, EN y ES)
-- ============================================================================
IF OBJECT_ID('dbo.amano_japon_transactions', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.amano_japon_transactions (
        id                          BIGINT IDENTITY(1,1) PRIMARY KEY,
        sede                        VARCHAR(30)     NOT NULL, -- pld, quillota, homecenter, plazuela, conquistadores
        fecha_reporte               DATE            NOT NULL, -- Fecha consultada en ExACT (YYYY-MM-DD)
        archivo_origen              VARCHAR(255)    NULL,
        fecha_carga                 DATETIME2(0)    NOT NULL DEFAULT SYSDATETIME(),

        -- Identificación y ubicación
        parking_lot                 NVARCHAR(100)   NOT NULL,
        area_id                     INT             NULL,
        area_name                   NVARCHAR(100)   NULL,
        equipment                   NVARCHAR(100)   NULL,
        cashier                     NVARCHAR(100)   NULL,

        -- Contadores y equipos
        t_total_number              INT             NULL,
        paid_equipment_number       INT             NULL,
        entry_equipment_number      INT             NULL,
        exit_equipment_number       INT             NULL,

        -- Fechas operacionales (almacenadas como DATETIME2 nativo sin ambigüedad)
        payment_date                DATETIME2(0)    NULL,
        entry_date                  DATETIME2(0)    NULL,
        exit_date                   DATETIME2(0)    NULL,

        -- Clasificación y montos principales
        payment_type                NVARCHAR(80)    NULL,
        card_type                   NVARCHAR(50)    NULL,
        fee_rate_pass_card_type     NVARCHAR(50)    NULL,
        card_number                 VARCHAR(50)     NULL,
        parking_fee                 DECIMAL(12, 2)  NOT NULL DEFAULT 0,
        payment                     DECIMAL(12, 2)  NOT NULL DEFAULT 0,
        credit                      DECIMAL(12, 2)  NOT NULL DEFAULT 0,

        -- Descuentos 1 al 9 (ordenados secuencialmente)
        card_type_1                 NVARCHAR(50)    NULL,
        discount_num_1              VARCHAR(50)     NULL,
        discount_1                  DECIMAL(12, 2)  NULL,
        card_type_2                 NVARCHAR(50)    NULL,
        discount_num_2              VARCHAR(50)     NULL,
        discount_2                  DECIMAL(12, 2)  NULL,
        card_type_3                 NVARCHAR(50)    NULL,
        discount_num_3              VARCHAR(50)     NULL,
        discount_3                  DECIMAL(12, 2)  NULL,
        card_type_4                 NVARCHAR(50)    NULL,
        discount_num_4              VARCHAR(50)     NULL,
        discount_4                  DECIMAL(12, 2)  NULL,
        card_type_5                 NVARCHAR(50)    NULL,
        discount_num_5              VARCHAR(50)     NULL,
        discount_5                  DECIMAL(12, 2)  NULL,
        card_type_6                 NVARCHAR(50)    NULL,
        discount_num_6              VARCHAR(50)     NULL,
        discount_6                  DECIMAL(12, 2)  NULL,
        card_type_7                 NVARCHAR(50)    NULL,
        discount_num_7              VARCHAR(50)     NULL,
        discount_7                  DECIMAL(12, 2)  NULL,
        card_type_8                 NVARCHAR(50)    NULL,
        discount_num_8              VARCHAR(50)     NULL,
        discount_8                  DECIMAL(12, 2)  NULL,
        card_type_9                 NVARCHAR(50)    NULL,
        discount_num_9              VARCHAR(50)     NULL,
        discount_9                  DECIMAL(12, 2)  NULL,

        -- Boletas fiscales 1 al 3 (Plazuela, PLD, Quillota)
        fiscal_receipt_no_1         VARCHAR(50)     NULL,
        fiscal_amount_1             DECIMAL(12, 2)  NULL,
        fiscal_receipt_no_2         VARCHAR(50)     NULL,
        fiscal_amount_2             DECIMAL(12, 2)  NULL,
        fiscal_receipt_no_3         VARCHAR(50)     NULL,
        fiscal_amount_3             DECIMAL(12, 2)  NULL
    );

    CREATE INDEX IX_amano_jp_tx_sede_fecha
        ON dbo.amano_japon_transactions (sede, fecha_reporte);

    CREATE INDEX IX_amano_jp_tx_payment_date
        ON dbo.amano_japon_transactions (parking_lot, payment_date);
END
GO

-- ============================================================================
-- 5. TABLA: AMANO JAPAN TRACKING (Unificada 17 columnas, EN y ES)
-- ============================================================================
IF OBJECT_ID('dbo.amano_japon_tracking', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.amano_japon_tracking (
        id                          BIGINT IDENTITY(1,1) PRIMARY KEY,
        sede                        VARCHAR(30)     NOT NULL, -- pld, quillota, homecenter, plazuela, conquistadores
        fecha_reporte               DATE            NOT NULL, -- Fecha consultada en ExACT (YYYY-MM-DD)
        archivo_origen              VARCHAR(255)    NULL,
        fecha_carga                 DATETIME2(0)    NOT NULL DEFAULT SYSDATETIME(),

        parking_lot                 NVARCHAR(100)   NOT NULL,
        card_type                   NVARCHAR(50)    NULL,
        card_number                 VARCHAR(50)     NULL,
        entry_equipment             NVARCHAR(100)   NULL,
        entry_date                  DATETIME2(0)    NULL,
        payment_equipment           NVARCHAR(100)   NULL,
        payment_date                DATETIME2(0)    NULL,
        exit_equipment              NVARCHAR(100)   NULL,
        exit_date                   DATETIME2(0)    NULL,
        fee_rate                    NVARCHAR(50)    NULL,
        parking_fee                 DECIMAL(12, 2)  NOT NULL DEFAULT 0,
        cash_sales                  DECIMAL(12, 2)  NOT NULL DEFAULT 0,
        credit_sales                DECIMAL(12, 2)  NOT NULL DEFAULT 0,
        disc_total                  DECIMAL(12, 2)  NOT NULL DEFAULT 0,
        misc_sales                  DECIMAL(12, 2)  NOT NULL DEFAULT 0,
        cashier                     NVARCHAR(100)   NULL,
        license_plate               VARCHAR(20)     NULL
    );

    CREATE INDEX IX_amano_jp_trk_sede_fecha
        ON dbo.amano_japon_tracking (sede, fecha_reporte);

    CREATE INDEX IX_amano_jp_trk_exit_date
        ON dbo.amano_japon_tracking (parking_lot, exit_date);
END
GO

-- ============================================================================
-- 6. TABLA: AUDITORÍA DE EJECUCIONES PARA EL DASHBOARD
-- ============================================================================
IF OBJECT_ID('dbo.bot_ejecuciones', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.bot_ejecuciones (
        id                  BIGINT IDENTITY(1,1) PRIMARY KEY,
        bot_name            VARCHAR(50)     NOT NULL,
        sede                VARCHAR(30)     NOT NULL,
        reporte             VARCHAR(50)     NOT NULL,
        fecha_reporte       DATE            NOT NULL,
        filas_insertadas    INT             NOT NULL DEFAULT 0,
        estado              VARCHAR(20)     NOT NULL, -- OK, SIN_DATOS, ERROR
        mensaje_error       NVARCHAR(500)   NULL,
        fecha_ejecucion     DATETIME2(0)    NOT NULL DEFAULT SYSDATETIME()
    );

    CREATE INDEX IX_bot_ejecuciones_consulta
        ON dbo.bot_ejecuciones (bot_name, sede, fecha_reporte);
END
GO

-- ============================================================================
-- 1. TABLA: redcomercio_cps_pagos (38 columnas Excel + metadatos)
-- ============================================================================
IF OBJECT_ID('dbo.redcomercio_cps_pagos', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.redcomercio_cps_pagos (
        id                              BIGINT IDENTITY(1,1) PRIMARY KEY,
        sede                            VARCHAR(30)     NOT NULL, -- 'redcomercio_cps'
        fecha_reporte                   DATE            NOT NULL,
        archivo_origen                  VARCHAR(255)    NULL,
        fecha_carga                     DATETIME2(0)    NOT NULL DEFAULT SYSDATETIME(),

        -- Identificación y ubicación
        pago_id                         BIGINT          NULL,
        transaccion_id                  BIGINT          NULL,
        empresa                         NVARCHAR(100)   NULL,
        sucursal                        NVARCHAR(100)   NULL,
        calza                           NVARCHAR(50)    NULL,
        patente                         VARCHAR(30)     NULL,
        operador                        NVARCHAR(150)   NULL,
        dispositivo                     NVARCHAR(150)   NULL,
        host                            NVARCHAR(150)   NULL,

        -- Tiempo y montos
        minutos                         INT             NULL,
        subtotal                        DECIMAL(12, 2)  NOT NULL DEFAULT 0,
        redondeo                        DECIMAL(12, 2)  NOT NULL DEFAULT 0,
        descuento                       DECIMAL(12, 2)  NOT NULL DEFAULT 0,
        monto                           DECIMAL(12, 2)  NOT NULL DEFAULT 0,
        nombre_descuento                NVARCHAR(150)   NULL,
        cupon_descuento                 NVARCHAR(100)   NULL,

        -- Fechas y documentos
        fecha_creacion                  DATETIME2(0)    NULL,
        fecha_exito_rechazo             DATETIME2(0)    NULL,
        folio                           VARCHAR(50)     NULL,
        estado                          NVARCHAR(80)    NULL,
        estado_sii                      VARCHAR(50)     NULL,

        -- Medio de pago y autorización
        medio_pago                      NVARCHAR(100)   NULL,
        tipo_tarjeta                    VARCHAR(50)     NULL,
        nro_tarjeta                     VARCHAR(50)     NULL,
        servicio                        NVARCHAR(100)   NULL,
        tipo_cobro                      NVARCHAR(100)   NULL,
        codigo_autorizacion             VARCHAR(80)     NULL,
        nro_operacion                   VARCHAR(80)     NULL,
        confirmacion                    NVARCHAR(80)    NULL,
        descripcion                     NVARCHAR(255)   NULL,
        rut_suscripcion                 VARCHAR(30)     NULL,
        url                             VARCHAR(255)    NULL,
        voucher_url                     VARCHAR(500)    NULL,

        -- Recarga Sonda
        recarga_sonda_id_tarjeta        VARCHAR(80)     NULL,
        recarga_sonda_id_tx_carga       VARCHAR(80)     NULL,
        recarga_sonda_anulada           VARCHAR(50)     NULL,
        recarga_sonda_id_tx_anulacion   VARCHAR(80)     NULL,
        recarga_sonda_saldo_actualizado DECIMAL(12, 2)  NULL
    );

    CREATE INDEX IX_rc_pagos_sede_fecha
        ON dbo.redcomercio_cps_pagos (sede, fecha_reporte);

    CREATE INDEX IX_rc_pagos_sucursal_fecha
        ON dbo.redcomercio_cps_pagos (sucursal, fecha_reporte);

    CREATE INDEX IX_rc_pagos_tx_id
        ON dbo.redcomercio_cps_pagos (transaccion_id);
END
GO

-- ============================================================================
-- 2. TABLA: redcomercio_cps_transacciones (39 columnas Excel + timestamps + metadatos)
-- ============================================================================
IF OBJECT_ID('dbo.redcomercio_cps_transacciones', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.redcomercio_cps_transacciones (
        id                              BIGINT IDENTITY(1,1) PRIMARY KEY,
        sede                            VARCHAR(30)     NOT NULL, -- 'redcomercio_cps'
        fecha_reporte                   DATE            NOT NULL,
        archivo_origen                  VARCHAR(255)    NULL,
        fecha_carga                     DATETIME2(0)    NOT NULL DEFAULT SYSDATETIME(),

        -- Identificación y fechas operacionales
        transaccion_id                  BIGINT          NULL,
        patente                         VARCHAR(30)     NULL,
        fecha_entrada                   DATE            NULL,
        hora_entrada                    VARCHAR(15)     NULL,
        fecha_hora_entrada              DATETIME2(0)    NULL,
        fecha_salida                    DATE            NULL,
        hora_salida                     VARCHAR(15)     NULL,
        fecha_hora_salida               DATETIME2(0)    NULL,
        fecha_cobro                     DATE            NULL,
        hora_cobro                      VARCHAR(15)     NULL,
        fecha_hora_cobro                DATETIME2(0)    NULL,

        -- Flujo y dispositivos
        tipo_transaccion                NVARCHAR(100)   NULL,
        metodo_ingreso                  NVARCHAR(100)   NULL,
        dispositivo_entrada             NVARCHAR(150)   NULL,
        dispositivo_salida              NVARCHAR(150)   NULL,

        -- Montos
        subtotal                        DECIMAL(12, 2)  NOT NULL DEFAULT 0,
        redondeo                        DECIMAL(12, 2)  NOT NULL DEFAULT 0,
        descuento                       DECIMAL(12, 2)  NOT NULL DEFAULT 0,
        cobrado                         DECIMAL(12, 2)  NOT NULL DEFAULT 0,
        saldo_administrativo            DECIMAL(12, 2)  NOT NULL DEFAULT 0,
        metodo_pago                     NVARCHAR(100)   NULL,

        -- Usuarios, ubicación y vehículo
        usuario_entrada                 NVARCHAR(150)   NULL,
        usuario_salida                  NVARCHAR(150)   NULL,
        sucursal                        NVARCHAR(100)   NULL,
        calza                           NVARCHAR(50)    NULL,
        tipo_vehiculo                   NVARCHAR(80)    NULL,
        minutos                         INT             NULL,
        nombre_descuento                NVARCHAR(150)   NULL,
        cupon_descuento                 NVARCHAR(100)   NULL,
        estado                          NVARCHAR(80)    NULL,
        comentario_entrada              NVARCHAR(255)   NULL,
        comentario_salida               NVARCHAR(255)   NULL,

        -- Tickets, LPR y referencias
        folio                           VARCHAR(50)     NULL,
        reimpresiones_ticket_salida     INT             NULL,
        cantidad_tickets_qr_impresos    INT             NULL,
        ticket_liberado                 VARCHAR(50)     NULL,
        dueno_tarjeta                   NVARCHAR(150)   NULL,
        lpr_entrada                     VARCHAR(30)     NULL,
        lpr_salida                      VARCHAR(30)     NULL,
        id_reserva                      VARCHAR(80)     NULL,
        url                             VARCHAR(255)    NULL,
        nro_ticket                      VARCHAR(80)     NULL
    );

    CREATE INDEX IX_rc_tx_sede_fecha
        ON dbo.redcomercio_cps_transacciones (sede, fecha_reporte);

    CREATE INDEX IX_rc_tx_sucursal_fecha
        ON dbo.redcomercio_cps_transacciones (sucursal, fecha_reporte);

    CREATE INDEX IX_rc_tx_id
        ON dbo.redcomercio_cps_transacciones (transaccion_id);
END
GO