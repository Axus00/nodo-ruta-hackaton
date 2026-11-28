--Insercion de datos inicial en tabla de pedidos
INSERT INTO pedidos
(id, zona, estado)
VALUES
('PED-001', 'Norte', 'En ruta'),
('PED-002', 'Centro', 'Entregado'),
('PED-003', 'Sur', 'Pendiente'),
('PED-004', 'Occidente', 'En ruta'),
('PED-005', 'Orient', 'Entregado'),
('PED-006', 'Centro', 'En preparación')
;
-- Actualizar el indice al actual
SELECT setval('pedidos_id_seq', 6);
