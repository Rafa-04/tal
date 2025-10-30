/*
 Navicat Premium Data Transfer

 Source Server         : software de optimizacion
 Source Server Type    : MySQL
 Source Server Version : 100432 (10.4.32-MariaDB)
 Source Host           : localhost:3306
 Source Schema         : conductor

 Target Server Type    : MySQL
 Target Server Version : 100432 (10.4.32-MariaDB)
 File Encoding         : 65001

 Date: 15/06/2025 12:54:39
*/

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- ----------------------------
-- Table structure for conductor
-- ----------------------------
DROP TABLE IF EXISTS `conductor`;
CREATE TABLE `conductor`  (
  `cedula` int NOT NULL,
  `nombre` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `apellido` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `licencia` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `fecha_registro` timestamp NOT NULL DEFAULT current_timestamp,
  `activo` tinyint(1) NULL DEFAULT 1,
  PRIMARY KEY (`cedula`) USING BTREE,
  INDEX `idx_nombre_completo`(`apellido` ASC, `nombre` ASC) USING BTREE,
  INDEX `idx_licencia`(`licencia` ASC) USING BTREE,
  INDEX `idx_activo`(`activo` ASC) USING BTREE
) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_general_ci ROW_FORMAT = Dynamic;

-- ----------------------------
-- Records of conductor
-- ----------------------------

-- ----------------------------
-- Table structure for linea
-- ----------------------------
DROP TABLE IF EXISTS `linea`;
CREATE TABLE `linea`  (
  `id` int NOT NULL AUTO_INCREMENT,
  `nombre` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `descripcion` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL,
  `imagen_logo` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL,
  `fecha_creacion` timestamp NOT NULL DEFAULT current_timestamp,
  `activa` tinyint(1) NULL DEFAULT 1,
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `idx_nombre_linea`(`nombre` ASC) USING BTREE,
  INDEX `idx_activa`(`activa` ASC) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 4 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_general_ci ROW_FORMAT = Dynamic;

-- ----------------------------
-- Records of linea
-- ----------------------------
INSERT INTO `linea` VALUES (1, 'Línea Centro', 'Ruta que conecta el centro de la ciudad con las zonas residenciales', NULL, '2025-06-15 12:00:30', 1);
INSERT INTO `linea` VALUES (2, 'Línea Norte', 'Servicio de transporte hacia la zona norte de la ciudad', NULL, '2025-06-15 12:00:30', 1);
INSERT INTO `linea` VALUES (3, 'Línea Sur', 'Cobertura de la zona sur y barrios periféricos', NULL, '2025-06-15 12:00:30', 1);

-- ----------------------------
-- Table structure for sistema_analitico
-- ----------------------------
DROP TABLE IF EXISTS `sistema_analitico`;
CREATE TABLE `sistema_analitico`  (
  `id` int NOT NULL AUTO_INCREMENT,
  `viaje_id` int NOT NULL,
  `tipo_analisis` enum('eficiencia','ruta_optima','tiempo_estimado','consumo') CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `resultado` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL,
  `puntuacion` decimal(3, 2) NULL DEFAULT NULL,
  `fecha_analisis` timestamp NOT NULL DEFAULT current_timestamp,
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `idx_viaje`(`viaje_id` ASC) USING BTREE,
  INDEX `idx_tipo`(`tipo_analisis` ASC) USING BTREE,
  INDEX `idx_fecha`(`fecha_analisis` ASC) USING BTREE,
  CONSTRAINT `sistema_analitico_ibfk_1` FOREIGN KEY (`viaje_id`) REFERENCES `viaje` (`id`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_general_ci ROW_FORMAT = Dynamic;

-- ----------------------------
-- Records of sistema_analitico
-- ----------------------------

-- ----------------------------
-- Table structure for usuario
-- ----------------------------
DROP TABLE IF EXISTS `usuario`;
CREATE TABLE `usuario`  (
  `id` int NOT NULL AUTO_INCREMENT,
  `nombre_usuario` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `contrasena` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `fecha_creacion` timestamp NOT NULL DEFAULT current_timestamp,
  `ultimo_acceso` timestamp NULL DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `nombre_usuario`(`nombre_usuario` ASC) USING BTREE,
  INDEX `idx_nombre_usuario`(`nombre_usuario` ASC) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 2 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_general_ci ROW_FORMAT = Dynamic;

-- ----------------------------
-- Records of usuario
-- ----------------------------
INSERT INTO `usuario` VALUES (1, 'admin', '$2b$12$ejemplo_hash_bcrypt_aqui', '2025-06-15 12:00:30', NULL);

-- ----------------------------
-- Table structure for vehiculo
-- ----------------------------
DROP TABLE IF EXISTS `vehiculo`;
CREATE TABLE `vehiculo`  (
  `matricula` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `marca` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `modelo` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL,
  `linea_asignada` int NULL DEFAULT NULL,
  `capacidad` int NOT NULL DEFAULT 0,
  `conductor_ci` int NOT NULL,
  `fecha_asignacion` timestamp NOT NULL DEFAULT current_timestamp,
  `activo` tinyint(1) NULL DEFAULT 1,
  PRIMARY KEY (`matricula`) USING BTREE,
  INDEX `idx_conductor`(`conductor_ci` ASC) USING BTREE,
  INDEX `idx_linea`(`linea_asignada` ASC) USING BTREE,
  INDEX `idx_marca`(`marca` ASC) USING BTREE,
  INDEX `idx_activo`(`activo` ASC) USING BTREE,
  CONSTRAINT `vehiculo_ibfk_1` FOREIGN KEY (`conductor_ci`) REFERENCES `conductor` (`cedula`) ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT `vehiculo_ibfk_2` FOREIGN KEY (`linea_asignada`) REFERENCES `linea` (`id`) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_general_ci ROW_FORMAT = Dynamic;

-- ----------------------------
-- Records of vehiculo
-- ----------------------------

-- ----------------------------
-- Table structure for viaje (actualizada con nuevas columnas)
-- ----------------------------
DROP TABLE IF EXISTS `viaje`;
CREATE TABLE `viaje` (
  `id` int NOT NULL AUTO_INCREMENT,
  `paradas` varchar(500) NOT NULL,
  `rutas_asignadas` varchar(500) NOT NULL,
  `distancia_destino` decimal(8,2) NOT NULL DEFAULT 0.00,
  `fecha_salida` datetime NOT NULL,
  `fecha_llegada` datetime NOT NULL,
  `vehiculo_id` varchar(20) NOT NULL,
  `conductor_ci` int NOT NULL,
  `estado` enum('programado','en_curso','completado','cancelado') DEFAULT 'programado',
  `fecha_creacion` timestamp NOT NULL DEFAULT current_timestamp(),
  `ruta_coordenadas` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `distancia_calculada` decimal(10,2) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_fechas` (`fecha_salida`,`fecha_llegada`),
  KEY `idx_conductor` (`conductor_ci`),
  KEY `idx_vehiculo` (`vehiculo_id`),
  KEY `idx_estado` (`estado`),
  KEY `idx_paradas_fecha` (`paradas`(100),`fecha_salida`),
  CONSTRAINT `viaje_ibfk_1` FOREIGN KEY (`conductor_ci`) REFERENCES `conductor` (`cedula`) ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT `viaje_ibfk_2` FOREIGN KEY (`vehiculo_id`) REFERENCES `vehiculo` (`matricula`) ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT `CONSTRAINT_1` CHECK (`fecha_llegada` > `fecha_salida`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- ----------------------------
-- Records of viaje
-- ----------------------------

SET FOREIGN_KEY_CHECKS = 1;