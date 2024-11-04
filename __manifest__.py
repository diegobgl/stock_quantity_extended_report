# -*- coding: utf-8 -*-
{
    'name': 'Stock Quantity Extended Report',
    'version': '14.0.1.0.0',
    'summary': 'Extiende el reporte de Inventario a la Fecha para incluir ubicación, tipo de movimiento, y más.',
    'description': 'Módulo para extender el reporte de inventario a la fecha en Odoo, incluyendo información adicional como ubicación, tipo de movimiento, lote/número de serie, y valor total.',
    'author': 'Diego',
    'depends': ['stock'],
    'data': [
        'views/stock_quantity_history_views.xml',
    ],
    'installable': True,
    'application': False,
}
