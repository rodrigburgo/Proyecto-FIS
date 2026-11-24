"""RF-01, RF-10: usuarios, roles, autenticacion (UsuarioRepository + AuthService)."""
import hashlib
import hmac
import os
from dataclasses import dataclass

from sqlalchemy import insert, select, update
from sqlalchemy.exc import IntegrityError

from . import auditoria
from .config import ADMIN_INICIAL, ANALISTA_INICIAL, PERMISOS, ROLES
from .db import engine, usuarios


@dataclass
class Usuario:
    id: int
    nombre: str
    correo: str
    documento: str
    rol: str
    activo: bool


class UsuarioYaExiste(Exception):
    pass


def hash_clave(clave: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", clave.encode(), salt, 200_000)
    return f"{salt.hex()}${dk.hex()}"


def verificar_clave(clave: str, almacenado: str) -> bool:
    try:
        salt_hex, dk_hex = almacenado.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", clave.encode(), bytes.fromhex(salt_hex), 200_000)
        return hmac.compare_digest(dk.hex(), dk_hex)
    except Exception:
        return False


def _a_usuario(r) -> Usuario:
    return Usuario(r.id, r.nombre, r.correo, r.documento, r.rol, bool(r.activo))


class UsuarioRepository:
    def existe(self, correo: str, documento: str) -> bool:
        with engine.connect() as c:
            q = select(usuarios.c.id).where((usuarios.c.correo == correo.lower()) | (usuarios.c.documento == documento))
            return c.execute(q).first() is not None

    def crear(self, nombre, correo, documento, clave, rol) -> int:
        if rol not in ROLES:
            raise ValueError("Rol invalido")
        if self.existe(correo, documento):
            raise UsuarioYaExiste("El usuario ya existe (correo o documento duplicado).")
        try:
            with engine.begin() as c:
                res = c.execute(insert(usuarios).values(
                    nombre=nombre.strip(), correo=correo.strip().lower(), documento=documento.strip(),
                    clave_hash=hash_clave(clave), rol=rol, activo=1))
                return res.inserted_primary_key[0]
        except IntegrityError as e:
            raise UsuarioYaExiste("El usuario ya existe (correo o documento duplicado).") from e

    def por_correo(self, correo: str):
        with engine.connect() as c:
            return c.execute(select(usuarios).where(usuarios.c.correo == correo.strip().lower())).first()

    def por_id(self, id_: int):
        with engine.connect() as c:
            return c.execute(select(usuarios).where(usuarios.c.id == id_)).first()

    def listar(self) -> list[Usuario]:
        with engine.connect() as c:
            return [_a_usuario(r) for r in c.execute(select(usuarios).order_by(usuarios.c.id))]

    def actualizar_rol(self, id_, rol):
        with engine.begin() as c:
            c.execute(update(usuarios).where(usuarios.c.id == id_).values(rol=rol))

    def set_activo(self, id_, activo: bool):
        with engine.begin() as c:
            c.execute(update(usuarios).where(usuarios.c.id == id_).values(activo=1 if activo else 0))

    def set_clave(self, id_, clave):
        with engine.begin() as c:
            c.execute(update(usuarios).where(usuarios.c.id == id_).values(clave_hash=hash_clave(clave)))


class AuthService:
    def __init__(self):
        self.repo = UsuarioRepository()

    def autenticar(self, correo: str, clave: str):
        """Devuelve (Usuario | None, mensaje). Estados: ValidandoCredenciales -> VerificandoEstado -> Exito/Fallo."""
        r = self.repo.por_correo(correo)
        if r is None or not verificar_clave(clave, r.clave_hash):
            auditoria.registrar(r.id if r else None, "LOGIN_FALLIDO", correo)
            return None, "Credenciales incorrectas."
        if not r.activo:
            auditoria.registrar(r.id, "LOGIN_FALLIDO", "cuenta inactiva")
            return None, "La cuenta está inactiva."
        auditoria.registrar(r.id, "LOGIN_EXITOSO", "")
        return _a_usuario(r), "ok"

    def cambiar_clave(self, usuario: Usuario, actual: str, nueva: str):
        r = self.repo.por_id(usuario.id)
        if not verificar_clave(actual, r.clave_hash):
            return False, "La contraseña actual no es correcta."
        if len(nueva) < 8:
            return False, "La nueva contraseña debe tener al menos 8 caracteres."
        self.repo.set_clave(usuario.id, nueva)
        auditoria.registrar(usuario.id, "CLAVE_CAMBIADA", "")
        return True, "Contraseña actualizada."


def puede_acceder(rol: str, pagina: str) -> bool:
    return rol in PERMISOS.get(pagina, [])


def sembrar_usuarios_iniciales():
    repo = UsuarioRepository()
    if not repo.listar():
        for nombre, correo, doc, clave, rol in (ADMIN_INICIAL, ANALISTA_INICIAL):
            repo.crear(nombre, correo, doc, clave, rol)
