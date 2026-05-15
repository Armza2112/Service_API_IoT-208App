"""
Auto-import all entity files in this package.

วิธีเพิ่ม Entity ใหม่:
  1. สร้างไฟล์ใน app/entities/  เช่น  sensor_data_entity.py
  2. ประกาศ class ที่ inherit db.Model
  3. รีสตาร์ท server — ตาราง DB จะถูกสร้างอัตโนมัติ
  ไม่ต้องแก้ไฟล์อื่นใดเพิ่มเติม
"""
import importlib
import pkgutil
from pathlib import Path

_package_dir = Path(__file__).parent
for _module_info in pkgutil.iter_modules([str(_package_dir)]):
    importlib.import_module(f"app.entities.{_module_info.name}")
