# Sistema de Logs Multi Base de Datos

## Descripción

El **Sistema de Logs Multi Base de Datos** es una aplicación desarrollada para registrar, almacenar y visualizar eventos (logs) provenientes de diferentes aplicaciones o servicios utilizando múltiples motores de bases de datos.

La principal característica del sistema es la capacidad de cambiar dinámicamente el motor de almacenamiento sin interrumpir el servicio ni perder información. Esto permite evaluar diferentes tecnologías de bases de datos bajo una misma plataforma y centralizar la administración de los registros generados por distintas aplicaciones.

El proyecto implementa una arquitectura basada en servicios, donde un backend desarrollado con FastAPI administra las conexiones, el almacenamiento y la consulta de los registros, mientras que un frontend desarrollado con React permite la administración y visualización de la información.

---

# Objetivo General

Desarrollar una plataforma capaz de registrar, almacenar y visualizar registros (logs) utilizando diferentes motores de bases de datos, permitiendo cambiar el destino de almacenamiento en tiempo real sin afectar la disponibilidad ni la integridad de la información.

---

# Objetivos Específicos

- Registrar eventos generados por diferentes aplicaciones.
- Almacenar registros utilizando distintos motores de bases de datos.
- Permitir el cambio dinámico del motor de almacenamiento.
- Visualizar los registros desde una única interfaz.
- Mantener la integridad de la información durante los cambios de conexión.
- Facilitar la administración de conexiones y fuentes de datos.

---

# Características principales

- Registro de logs en tiempo real.
- Compatibilidad con múltiples motores de bases de datos.
- Cambio de base de datos sin pérdida de información.
- API REST para la administración del sistema.
- Dashboard para visualizar registros.
- Gestión de conexiones.
- Gestión de fuentes de datos.
- Historial de cambios de conexión.
- Consultas filtradas por diferentes criterios.
- Pruebas automáticas del sistema.

---

# Arquitectura del Proyecto

El sistema está compuesto por tres componentes principales:

- Frontend desarrollado en React + Vite.
- Backend desarrollado con FastAPI.
- Motores de bases de datos conectados mediante Docker Compose.

El backend actúa como intermediario entre las aplicaciones que generan los logs y el motor de almacenamiento seleccionado.

La metadata del sistema se almacena en SQLite, mientras que los registros pueden almacenarse en diferentes motores según la configuración activa.

---

# Motores de Base de Datos Soportados

Actualmente el sistema soporta:

- MariaDB
- PostgreSQL
- Microsoft SQL Server
- MongoDB
- Redis
- SQLite (metadata)

---

# Tecnologías Utilizadas

## Backend

- Python 3.12
- FastAPI
- Uvicorn
- SQLAlchemy (si aplica)
- Pydantic

## Frontend

- React
- TypeScript
- Vite

## Bases de Datos

- MariaDB
- PostgreSQL
- SQL Server
- MongoDB
- Redis
- SQLite

## Infraestructura

- Docker
- Docker Compose

---

# Requisitos

Para ejecutar el proyecto se requiere:

- Docker Desktop
- Docker Compose
- Python 3.12 (para desarrollo)
- Git

---

# Instalación

## 1. Clonar el repositorio

```bash
git clone URL_DEL_REPOSITORIO
```

## 2. Entrar al proyecto

```bash
cd logmon
```

## 3. Configurar las variables de entorno

Copiar el archivo

```text
.env.example
```

como

```text
.env
```

y configurar las credenciales correspondientes.

## 4. Levantar los servicios

```bash
docker compose up -d
```

## 5. Ejecutar datos de prueba

```bash
make seed
```

---

# Uso del Sistema

Una vez iniciado el proyecto se podrá:

- Registrar nuevas conexiones.
- Asociar aplicaciones con una conexión.
- Cambiar el motor de almacenamiento.
- Registrar eventos.
- Consultar registros históricos.
- Visualizar el detalle de cada log.

---

# Flujo General

1. Una aplicación genera un evento.
2. El backend recibe la solicitud.
3. El Router determina el motor correspondiente.
4. El Adapter guarda el registro.
5. El usuario consulta los registros desde la interfaz web.

---

# Estructura del Proyecto

```text
logmon/

├── backend/
├── frontend/
├── docker-compose.yml
├── README.md
├── Makefile
└── .env.example
```

---

# API

## Endpoints principales

| Método | Endpoint | Descripción |
|---------|----------|-------------|
| POST | /api/logs | Registrar log |
| GET | /api/logs | Consultar logs |
| GET | /api/logs/{id} | Obtener detalle |
| POST | /api/logs/demo | Crear datos de prueba |
| POST | /api/sources/{id}/switch | Cambiar motor |
| POST | /api/connections/{id}/test | Probar conexión |

# Ejemplo de Funcionamiento

1. Crear una conexión.
2. Asociar una aplicación.
3. Registrar varios logs.
4. Cambiar el motor de almacenamiento.
5. Registrar nuevos logs.
6. Verificar que todos los registros continúan disponibles.

---

# Pruebas

El proyecto contempla pruebas para verificar:

- Funcionamiento de cada Adapter.
- Cambio de motor sin pérdida de información.
- Escrituras concurrentes.
- Consultas entre múltiples bases de datos.

# Licencia

> Pendiente de definir por el equipo de desarrollo.

---

# Agradecimientos

Este proyecto fue desarrollado como parte del curso correspondiente, con el objetivo de implementar una solución de monitoreo de registros utilizando múltiples motores de bases de datos y demostrar la flexibilidad de una arquitectura desacoplada para el almacenamiento y consulta de información.




