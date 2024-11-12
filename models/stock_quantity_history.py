from odoo import models, fields, api, _
from odoo.tools.misc import format_datetime
from odoo.osv import expression


class StockQuantityHistoryExtended(models.TransientModel):
    _inherit = 'stock.quantity.history'

    location_id = fields.Many2one(
        'stock.location', string="Ubicación",
        domain="[('usage', 'in', ['internal', 'transit'])]"
    )

    def open_detailed_view(self):
        """
        Consulta alternativa que utiliza stock.quants para mostrar productos, ubicaciones y lotes.
        """
        tree_view_id = self.env.ref('stock.view_stock_quant_tree').id  # Vista original de stock.quant

        domain = [('product_id.type', '=', 'product')]
        if self.inventory_datetime:
            domain.append(('in_date', '<=', self.inventory_datetime))  # Filtra por fecha
        if self.location_id:
            domain.append(('location_id', '=', self.location_id.id))  # Filtra por ubicación si está especificada

        action = {
            'type': 'ir.actions.act_window',
            'name': _('Detailed Product Quantities'),
            'res_model': 'stock.quant',
            'view_mode': 'tree',
            'views': [(tree_view_id, 'tree')],
            'domain': domain,
            'context': dict(self.env.context, to_date=self.inventory_datetime),
        }
        return action


    def open_at_date(self):
        active_model = self.env.context.get('active_model')

        if active_model == 'stock.valuation.layer':
            # Obtener la acción original
            action = self.env["ir.actions.actions"]._for_xml_id("stock_account.stock_valuation_layer_action")

            # Configuración de vistas
            tree_view = self.env.ref('your_module.stock_valuation_layer_valuation_at_date_tree_extended', raise_if_not_found=False)
            graph_view = self.env.ref('stock_account.stock_valuation_layer_graph', raise_if_not_found=False)
            action['views'] = [
                (tree_view.id if tree_view else False, 'tree'),
                (self.env.ref('stock_account.stock_valuation_layer_form').id, 'form'),
                (self.env.ref('stock_account.stock_valuation_layer_pivot').id, 'pivot'),
                (graph_view.id if graph_view else False, 'graph')
            ]

            # Modificar el dominio para incluir `location_id` si está especificado
            domain = [('create_date', '<=', self.inventory_datetime), ('product_id.type', '=', 'product')]
            if self.location_id:
                domain.append(('location_id', '=', self.location_id.id))

            action['domain'] = domain
            action['display_name'] = format_datetime(self.env, self.inventory_datetime)
            action['context'] = {"to_date": self.inventory_datetime}

            return action

        # Comportamiento original para otros modelos
        return super(StockQuantityHistoryExtended, self).open_at_date()



class ProductProduct(models.Model):
    _inherit = 'product.product'

    location_ids = fields.Many2many(
        'stock.location', string='Ubicaciones',
        compute='_compute_location_ids', store=False
    )

    lot_ids = fields.Many2many(
        'stock.lot', string='Lotes Disponibles',
        compute='_compute_lot_ids', store=False
    )

    valuation_account_id = fields.Many2one(
        'account.account', 
        string="Cuenta Contable de Valorización",
        related='categ_id.property_stock_valuation_account_id', 
        store=True,
        readonly=True
    )
    last_move_date = fields.Datetime(
        string='Fecha Último Movimiento',
        compute='_compute_last_move_date', store=False
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
        compute='_compute_unit_value',
        store=False
    )

    total_valuation = fields.Float(
        string='Valor Total Valorizado',
        compute='_compute_total_valuation',
        store=False
    )

    def _compute_total_valuation(self):
        for product in self:
            # Obtener todos los quants del producto que tienen cantidad disponible
            quant_records = self.env['stock.quant'].search([('product_id', '=', product.id), ('quantity', '>', 0)])
            # Calcular el valor total valorizado
            product.total_valuation = sum(quant.quantity * quant.product_id.standard_price for quant in quant_records)

    def _compute_unit_value(self):
        for product in self:
            quant_records = self.env['stock.quant'].search([('product_id', '=', product.id), ('quantity', '>', 0)])
            total_quantity = sum(quant.quantity for quant in quant_records)
            total_value = sum(quant.quantity * quant.product_id.standard_price for quant in quant_records)
            product.unit_val

    def _compute_location_ids(self):
        """Computa las ubicaciones donde está disponible el producto hasta la fecha consultada."""
        to_date = self.env.context.get('to_date')  # Fecha límite para consultar disponibilidad
        for product in self:
            domain = [('product_id', '=', product.id), ('quantity', '>', 0)]
            if to_date:
                domain.append(('in_date', '<=', to_date))  # Considerar solo movimientos hasta la fecha
            quants = self.env['stock.quant'].search(domain)
            product.location_ids = quants.mapped('location_id')

    def _compute_lot_ids(self):
        """Computa los lotes disponibles para el producto hasta la fecha consultada."""
        to_date = self.env.context.get('to_date')  # Fecha límite para consultar disponibilidad
        for product in self:
            # Filtrar quants por producto y fecha
            domain = [('product_id', '=', product.id), ('quantity', '>', 0)]
            if to_date:
                domain.append(('in_date', '<=', to_date))  # Considerar solo movimientos hasta la fecha
            quants = self.env['stock.quant'].search(domain)

            # Obtener lotes válidos y asegurarse de que existan
            lot_ids = quants.mapped('lot_id').filtered(lambda lot: lot.exists())  # Filtra lotes válidos
            if lot_ids:
                product.lot_ids = [(6, 0, lot_ids.ids)]  # Asignar correctamente valores a un campo Many2many
            else:
                product.lot_ids = [(5,)]  # Limpia el campo si no hay lotes válidos

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
            quant_records = self.env['stock.quant'].search([('product_id', '=', product.id)])
            quantity = sum(quant_records.mapped('quantity'))
            product.valuation_value = quantity * product.standard_price

    def _compute_last_move_date(self):
        """
        Calcula la fecha del último movimiento relacionado con el producto hasta la fecha de consulta.
        """
        to_date = self.env.context.get('to_date')  # Fecha límite para la consulta
        for product in self:
            domain = [
                ('product_id', '=', product.id),
                ('state', '=', 'done')
            ]
            if to_date:
                domain.append(('date', '<=', to_date))  # Considerar solo movimientos hasta la fecha

            # Buscar el movimiento más reciente hasta la fecha de consulta
            last_move = self.env['stock.move'].search(
                domain,
                order='date desc',
                limit=1
            )
            product.last_move_date = last_move.date if last_move else False


class StockQuant(models.Model):
    _inherit = 'stock.quant'

    valuation_value = fields.Float(
        string='Valorizado',
        compute='_compute_valuation_value',
        store=False
    )

    weighted_average_price = fields.Float(
        string='Precio Promedio Ponderado',
        compute='_compute_weighted_average_price',
        store=False
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
        string='Cuenta Contable',
        compute='_compute_valuation_account', store=False
    )

    move_type = fields.Selection(
        [('purchase', 'Compra'), ('internal', 'Transferencia Interna')],
        string='Tipo Movimiento',
        compute='_compute_move_info', store=False
    )

    last_move_date = fields.Datetime(
        string='Último Movimiento',
        compute='_compute_last_move_date', store=False
    )

    def _compute_valuation_value(self):
        """
        Calcula el valor total valorizado para cada `stock.quant`.
        """
        for quant in self:
            price_unit = quant.weighted_average_price or quant.product_id.standard_price
            quant.valuation_value = max(quant.quantity, 0) * price_unit

    def _compute_weighted_average_price(self):
        """
        Calcula el precio promedio ponderado para cada `stock.quant`.
        """
        for quant in self:
            product = quant.product_id
            total_value = 0.0
            total_quantity = 0.0

            # Filtrar movimientos relevantes
            domain = [('product_id', '=', product.id), ('state', '=', 'done')]
            to_date = self.env.context.get('to_date')
            if to_date:
                domain.append(('date', '<=', to_date))

            moves = self.env['stock.move'].search(domain)
            for move in moves:
                if move.picking_type_id.code in ['incoming', 'inventory']:
                    total_value += move.price_unit * move.product_qty
                    total_quantity += move.product_qty
                elif move.picking_type_id.code == 'outgoing':
                    total_quantity -= move.product_qty

            quant.weighted_average_price = total_value / total_quantity if total_quantity > 0 else product.standard_price

    @api.depends('product_id')
    def _compute_unit_value(self):
        for quant in self:
            quant.unit_value = quant.product_id.standard_price

    @api.depends('quantity', 'unit_value')
    def _compute_total_valuation(self):
        for quant in self:
            quant.total_valuation = quant.quantity * quant.unit_value

    @api.depends('product_id')
    def _compute_valuation_account(self):
        for quant in self:
            quant.valuation_account_id = quant.product_id.categ_id.property_stock_valuation_account_id

    @api.depends('product_id')
    def _compute_move_info(self):
        for quant in self:
            last_move = self.env['stock.move'].search(
                [('product_id', '=', quant.product_id.id)],
                order='date desc',
                limit=1
            )
            if last_move:
                quant.move_type = 'purchase' if last_move.picking_type_id.code == 'incoming' else 'internal'
            else:
                quant.move_type = False

    @api.depends('product_id')
    def _compute_last_move_date(self):
        for quant in self:
            last_move = self.env['stock.move'].search(
                [('product_id', '=', quant.product_id.id)],
                order='date desc',
                limit=1
            )
            quant.last_move_date = last_move.date if last_move else False




class StockValuationLayer(models.Model):
    _inherit = 'stock.valuation.layer'

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
        string='Cuenta Contable',
        compute='_compute_valuation_account', store=False
    )

    move_type = fields.Selection(
        [('purchase', 'Compra'), ('internal', 'Transferencia Interna')],
        string='Tipo Movimiento',
        compute='_compute_move_type', store=False
    )

    last_move_date = fields.Datetime(
        string='Último Movimiento',
        compute='_compute_last_move_date', store=False
    )

    location_id = fields.Many2one(
        'stock.location',
        string='Ubicación',
        compute='_compute_location_id',
        store=True,
    )

    def _compute_location_id(self):
        """
        Determina la ubicación real del producto basada en la cantidad disponible a la fecha.
        """
        for record in self:
            if record.product_id:
                # Usar un query SQL directo para mejorar rendimiento
                self.env.cr.execute("""
                    SELECT sq.location_id
                    FROM stock_quant sq
                    WHERE sq.product_id = %s
                    AND sq.quantity > 0
                    AND sq.in_date <= %s
                    ORDER BY sq.in_date DESC
                    LIMIT 1
                """, (record.product_id.id, record.create_date))

                result = self.env.cr.fetchone()
                record.location_id = result[0] if result else False
            else:
                record.location_id = False


    @api.depends('product_id')
    def _compute_unit_value(self):
        """
        Calcula el precio promedio unitario para el producto.
        """
        for layer in self:
            layer.unit_value = layer.product_id.standard_price

    @api.depends('quantity', 'unit_value')
    def _compute_total_valuation(self):
        """
        Calcula el valor total valorizado para el producto en el `valuation.layer`.
        """
        for layer in self:
            layer.total_valuation = layer.quantity * layer.unit_value

    @api.depends('product_id')
    def _compute_valuation_account(self):
        """
        Obtiene la cuenta contable asociada a la categoría del producto.
        """
        for layer in self:
            layer.valuation_account_id = layer.product_id.categ_id.property_stock_valuation_account_id

    @api.depends('product_id')
    def _compute_move_type(self):
        """
        Determina el tipo de movimiento asociado al producto.
        """
        for layer in self:
            last_move = self.env['stock.move'].search(
                [('product_id', '=', layer.product_id.id)],
                order='date desc',
                limit=1
            )
            if last_move:
                layer.move_type = 'purchase' if last_move.picking_type_id.code == 'incoming' else 'internal'
            else:
                layer.move_type = False

    @api.depends('product_id')
    def _compute_last_move_date(self):
        """
        Obtiene la fecha del último movimiento del producto.
        """
        for layer in self:
            last_move = self.env['stock.move'].search(
                [('product_id', '=', layer.product_id.id)],
                order='date desc',
                limit=1
            )
            layer.last_move_date = last_move.date if last_move else False
