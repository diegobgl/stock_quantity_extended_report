from odoo import models, fields, api, _
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
            'group_by': ['location_id', 'product_id'],  # Agrupar primero por ubicación y luego por producto
        }

        return action

class ProductProduct(models.Model):
    _inherit = 'product.product'

    location_ids = fields.Many2many(
        'stock.location', string='Locations',
        compute='_compute_location_ids', store=False
    )

    last_move_date = fields.Datetime(
        string='Fecha Último Movimiento',
        compute='_compute_last_move_info', store=False
    )

    move_type = fields.Selection(
        [('purchase', 'Compra'), ('internal', 'Transferencia Interna')],
        string='Tipo Movimiento',
        compute='_compute_last_move_info', store=False
    )

    valuation_value = fields.Float(
        string='Valorizado',
        compute='_compute_valuation_value', store=False
    )

    def _compute_location_ids(self):
        for product in self:
            # Obtener todas las ubicaciones donde se encuentra este producto
            quant_records = self.env['stock.quant'].search([('product_id', '=', product.id)])
            product.location_ids = quant_records.mapped('location_id')

    def _compute_last_move_info(self):
        for product in self:
            # Obtener el movimiento más reciente relacionado con el producto
            last_move = self.env['stock.move'].search(
                [('product_id', '=', product.id)],
                order='date desc',
                limit=1
            )
            if last_move:
                product.last_move_date = last_move.date
                product.move_type = 'purchase' if last_move.picking_type_id.code == 'incoming' else 'internal'
            else:
                product.last_move_date = False
                product.move_type = False

    def _compute_valuation_value(self):
        for product in self:
            # Obtener la cantidad disponible desde `stock.quant`
            quant_records = self.env['stock.quant'].search([('product_id', '=', product.id)])
            quantity = sum(quant_records.mapped('quantity'))
            # Valorización = Cantidad * Costo Unitario
            product.valuation_value = quantity * product.standard_price




class StockQuant(models.Model):
    _inherit = 'stock.quant'

    last_move_date = fields.Datetime(
        string='Fecha Último Movimiento',
        compute='_compute_last_move_info', store=False
    )

    move_type = fields.Selection(
        [('purchase', 'Compra'), ('internal', 'Transferencia Interna')],
        string='Tipo Movimiento',
        compute='_compute_last_move_info', store=False
    )

    valuation_value = fields.Float(
        string='Valorizado',
        compute='_compute_valuation_value', store=False
    )

    account_valuation_id = fields.Many2one(
        'account.account', string='Cuenta Contable de Valorización',
        compute='_compute_account_valuation', store=False
    )

    weighted_average_price = fields.Float(
        string='Precio Unitario',
        compute='_compute_weighted_average_price', store=False
    )

    def _compute_last_move_info(self):
        for quant in self:
            # Obtener el movimiento más reciente relacionado con el producto y ubicación específica del `quant`
            last_move = self.env['stock.move'].search(
                [('product_id', '=', quant.product_id.id), ('location_dest_id', '=', quant.location_id.id)],
                order='date desc',
                limit=1
            )
            if last_move:
                quant.last_move_date = last_move.date
                quant.move_type = 'purchase' if last_move.picking_type_id.code == 'incoming' else 'internal'
            else:
                quant.last_move_date = False
                quant.move_type = False

    def _compute_weighted_average_price(self):
        for quant in self:
            product = quant.product_id

            # Inicializar variables para el cálculo del precio promedio ponderado
            total_value = 0.0
            total_quantity = 0.0

            # Buscar movimientos de stock hasta la fecha actual
            moves = self.env['stock.move'].search([
                ('product_id', '=', product.id),
                ('state', '=', 'done'),
                ('date', '<=', fields.Datetime.now())  # Ajustamos para calcular hasta la fecha actual
            ])

            # Calcular el valor y cantidad total de los movimientos
            for move in moves:
                if move.picking_type_id.code == 'incoming':  # Compras o entradas
                    total_value += move.price_unit * move.product_qty
                    total_quantity += move.product_qty
                elif move.picking_type_id.code == 'outgoing':  # Salidas o ventas
                    total_quantity -= move.product_qty

            # Determinar el precio promedio ponderado
            if total_quantity > 0:
                quant.weighted_average_price = total_value / total_quantity
            else:
                # Si no hay movimientos relevantes, usar el precio estándar del producto
                quant.weighted_average_price = product.standard_price if product.standard_price > 0 else 0.0

    def _compute_valuation_value(self):
        for quant in self:
            # Asegurarse de que el precio unitario no sea cero antes de calcular la valorización
            price_unit = quant.weighted_average_price if quant.weighted_average_price > 0 else quant.product_id.standard_price
            quant.valuation_value = quant.quantity * price_unit

    def _compute_account_valuation(self):
        for quant in self:
            # Obtener la cuenta contable de valorización desde la categoría del producto
            quant.account_valuation_id = quant.product_id.categ_id.property_stock_valuation_account_id
