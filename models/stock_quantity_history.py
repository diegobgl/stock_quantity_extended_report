from odoo import models, fields, api
from odoo.tools.misc import format_datetime
from odoo.osv import expression

class StockQuantityHistory(models.TransientModel):
    _inherit = 'stock.quantity.history'

    def open_at_date(self):
        """
        Extiende el método para incluir el campo de ubicación (`location_id`)
        en la visualización de los productos a una fecha específica.
        """
        # Llamar al método original para mantener la lógica base
        tree_view_id = self.env.ref('stock.view_stock_product_tree').id
        form_view_id = self.env.ref('stock.product_form_view_procurement_button').id
        domain = [('type', '=', 'product')]

        # Usar contexto para manejar productos específicos
        product_id = self.env.context.get('product_id', False)
        product_tmpl_id = self.env.context.get('product_tmpl_id', False)

        if product_id:
            domain = expression.AND([domain, [('id', '=', product_id)]])
        elif product_tmpl_id:
            domain = expression.AND([domain, [('product_tmpl_id', '=', product_tmpl_id)]])

        # Aquí definimos la lógica para extender la vista con la información de ubicación
        action = {
            'type': 'ir.actions.act_window',
            'views': [(tree_view_id, 'tree'), (form_view_id, 'form')],
            'view_mode': 'tree,form',
            'name': _('Products'),
            'res_model': 'product.product',
            'domain': domain,
            'context': dict(self.env.context, to_date=self.inventory_datetime),
            'display_name': format_datetime(self.env, self.inventory_datetime)
        }

        # Modificación para incluir `location_id` utilizando stock.quant
        product_quant = self.env['stock.quant'].search([('product_id', 'in', product_id)])
        # Puedes filtrar las ubicaciones específicas si es necesario, aquí se muestra el primer resultado
        if product_quant:
            action['context'].update({
                'location_id': product_quant.location_id.id,
            })

        return action
    

class ProductProduct(models.Model):
    _inherit = 'product.product'

    location_id = fields.Many2one(
        'stock.location', string='Location',
        compute='_compute_location_id', store=False
    )

    def _compute_location_id(self):
        for product in self:
            # Busca la ubicación asociada al producto en el modelo `stock.quant`
            stock_quant = self.env['stock.quant'].search([('product_id', '=', product.id)], limit=1)
            product.location_id = stock_quant.location_id if stock_quant else False

