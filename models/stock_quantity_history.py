from odoo import models, fields, api, _
from odoo.tools.misc import format_datetime

class StockQuantityHistory(models.TransientModel):
    _inherit = 'stock.quantity.history'

    location_id = fields.Many2one(
        'stock.location',
        string="Ubicación",
        domain="[('usage', 'in', ['internal', 'transit'])]"
    )

    def open_at_date(self):
        """
        Modifica el método original para añadir la lógica de la ubicación sin alterar la consulta.
        """
        active_model = self.env.context.get('active_model')
        if active_model == 'stock.valuation.layer':
            # Llamar a la acción original
            action = self.env["ir.actions.actions"]._for_xml_id("stock_account.stock_valuation_layer_action")

            # Configurar las vistas
            tree_view = self.env.ref('stock_account.stock_valuation_layer_valuation_at_date_tree_inherited', raise_if_not_found=False)
            graph_view = self.env.ref('stock_account.stock_valuation_layer_graph', raise_if_not_found=False)
            action['views'] = [
                (tree_view.id if tree_view else False, 'tree'),
                (self.env.ref('stock_account.stock_valuation_layer_form').id, 'form'),
                (self.env.ref('stock_account.stock_valuation_layer_pivot').id, 'pivot'),
                (graph_view.id if graph_view else False, 'graph')
            ]

            # Modificar el dominio para incluir la ubicación si está especificada
            domain = [('create_date', '<=', self.inventory_datetime), ('product_id.type', '=', 'product')]
            if self.location_id:
                domain.append(('location_id', '=', self.location_id.id))

            action['domain'] = domain
            action['display_name'] = _("Inventory at %s") % self.inventory_datetime.strftime('%Y-%m-%d %H:%M:%S')
            action['context'] = "{}"

            return action

        # Lógica predeterminada para otros modelos
        return super(StockQuantityHistory, self).open_at_date()



class ProductProduct(models.Model):
    _inherit = 'product.product'

    location_ids = fields.Many2many(
        'stock.location', string='Ubicaciones',
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

    unit_value = fields.Float(
        string='Precio Promedio Unitario',
        compute='_compute_unit_value', store=False
    )

    total_valuation = fields.Float(
        string='Valor Total Valorizado',
        compute='_compute_total_valuation', store=False
    )

    valuation_account_id = fields.Many2one(
        'account.account',
        string='Cuenta Contable de Valorización',
        related='categ_id.property_stock_valuation_account_id',
        readonly=True,
        store=True
    )

    lot_ids = fields.Many2many(
        'stock.production.lot',
        string='Lotes Disponibles',
        compute='_compute_lot_ids'
    )

    def _compute_location_ids(self):
        for product in self:
            quants = self.env['stock.quant'].search([('product_id', '=', product.id), ('quantity', '>', 0)])
            product.location_ids = quants.mapped('location_id')

    def _compute_last_move_info(self):
        for product in self:
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
            quant_records = self.env['stock.quant'].search([('product_id', '=', product.id), ('quantity', '>', 0)])
            product.valuation_value = sum(quant.quantity * quant.product_id.standard_price for quant in quant_records)

    def _compute_unit_value(self):
        for product in self:
            quant_records = self.env['stock.quant'].search([('product_id', '=', product.id), ('quantity', '>', 0)])
            total_quantity = sum(quant.quantity for quant in quant_records)
            total_value = sum(quant.quantity * quant.product_id.standard_price for quant in quant_records)
            product.unit_value = total_value / total_quantity if total_quantity > 0 else 0.0

    def _compute_total_valuation(self):
        for product in self:
            quant_records = self.env['stock.quant'].search([('product_id', '=', product.id), ('quantity', '>', 0)])
            product.total_valuation = sum(quant.quantity * quant.product_id.standard_price for quant in quant_records)

    def _compute_lot_ids(self):
        for product in self:
            # Filtrar quants relacionados con el producto
            quants = self.env['stock.quant'].search([
                ('product_id', '=', product.id),
                ('quantity', '>', 0)
            ])
            # Obtener los IDs de los lotes relacionados
            lot_ids = quants.mapped('lot_id').ids
            # Asignar los IDs al campo Many2many
            product.lot_ids = [(6, 0, lot_ids)]


class StockQuant(models.Model):
    _inherit = 'stock.quant'

    cost = fields.Float(
        string='Costo Unitario',
        compute='_compute_cost'
    )

    def _compute_cost(self):
        for quant in self:
            quant.cost = quant.product_id.standard_price
