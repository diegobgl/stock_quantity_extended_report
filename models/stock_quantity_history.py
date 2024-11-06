from odoo import  _, models, fields, api
from odoo.tools.misc import format_datetime
from odoo.osv import expression

class StockQuantityHistory(models.TransientModel):
    _inherit = 'stock.quantity.history'

    def open_at_date(self):
        """
        Modificación del método `open_at_date` para agrupar primero por ubicación y luego por producto.
        """
        # Obtenemos la vista tree de `stock.quant` que contiene información sobre las ubicaciones y productos
        tree_view_id = self.env.ref('stock.view_stock_quant_tree').id

        # Definimos la acción para abrir los resultados en la vista tree
        action = {
            'type': 'ir.actions.act_window',
            'views': [(tree_view_id, 'tree')],
            'view_mode': 'tree',
            'name': _('Product Quantities by Location'),
            'res_model': 'stock.quant',
            'domain': [('product_id.type', '=', 'product')],
            'context': dict(self.env.context, to_date=self.inventory_datetime),
            'display_name': format_datetime(self.env, self.inventory_datetime),
            'group_by': ['location_id'],  # Agrupar primero por ubicación
            'order_by': 'location_id',  # Ordenar por ubicación explícitamente
        }

        return action

    
class ProductProduct(models.Model):
    _inherit = 'product.product'

    location_ids = fields.Many2many(
        'stock.location', string='Locations',
        compute='_compute_location_ids', store=False
    )

    def _compute_location_ids(self):
        for product in self:
            # Obtener todas las ubicaciones donde se encuentra este producto
            quant_records = self.env['stock.quant'].search([('product_id', '=', product.id)])
            product.location_ids = quant_records.mapped('location_id')

