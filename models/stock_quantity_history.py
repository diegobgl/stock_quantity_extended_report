from odoo import models, fields, api, _

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

    def _compute_unit_value(self):
        for product in self:
            # Calcula el precio promedio ponderado basado en movimientos de stock
            quant_records = self.env['stock.quant'].search([('product_id', '=', product.id)])
            total_quantity = sum(quant_records.mapped('quantity'))
            total_value = sum(quant_records.mapped(lambda q: q.quantity * q.product_id.standard_price))
            product.unit_value = total_value / total_quantity if total_quantity > 0 else 0

    def _compute_total_valuation(self):
        for product in self:
            # Calcular el valor total valorizado considerando el inventario actual
            quant_records = self.env['stock.quant'].search([('product_id', '=', product.id)])
            product.total_valuation = sum(quant_records.mapped(lambda q: q.quantity * q.product_id.standard_price))
