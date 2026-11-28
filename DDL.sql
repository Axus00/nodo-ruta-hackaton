--Secuencia para el id de pedidos 
CREATE SEQUENCE pedidos_id_seq START 1;

-- Creacion de la tabla
CREATE TABLE pedidos (
    id VARCHAR(10) PRIMARY KEY DEFAULT ('PED-' || LPAD(nextval('pedidos_id_seq')::TEXT, 3, '0')),
    zona VARCHAR(15),
    estado VARCHAR(20),
    fechai TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    fechaa TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Crear la funcion que asigna la fecha actual
CREATE OR REPLACE FUNCTION actualizar_fechaa()
RETURNS TRIGGER AS $$
BEGIN
    NEW.fechaa = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Asociar la función a la tabla cada vez que haya un UPDATE
CREATE TRIGGER trigger_actualizar_pedidos
BEFORE UPDATE ON pedidos
FOR EACH ROW
EXECUTE FUNCTION actualizar_fechaa();
