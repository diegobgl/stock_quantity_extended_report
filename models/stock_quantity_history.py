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
        """
        Abre la vista en 'stock.valuation.layer' mostrando solo registros con asientos contables relacionados.
        """
        active_model = self.env.context.get('active_model')

        if active_model == 'stock.valuation.layer':
            # Obtener la acción original
            action = self.env["ir.actions.actions"]._for_xml_id("stock_account.stock_valuation_layer_action")

            # Configuración de vistas
            tree_view = self.env.ref('stock_account.view_stock_valuation_layer_tree', raise_if_not_found=False)
            form_view = self.env.ref('stock_account.stock_valuation_layer_form', raise_if_not_found=False)
            pivot_view = self.env.ref('stock_account.stock_valuation_layer_pivot', raise_if_not_found=False)

            action['views'] = [
                (tree_view.id if tree_view else False, 'tree'),
                (form_view.id if form_view else False, 'form'),
                (pivot_view.id if pivot_view else False, 'pivot')
            ]

            # Crear un dominio para filtrar solo los registros con movimientos asociados a asientos contables
            domain = [
                ('create_date', '<=', self.inventory_datetime),
                ('product_id.type', '=', 'product'),
                ('account_move_id', '!=', False)  # Filtrar registros con asiento contable
            ]
            if self.location_id:
                domain.append(('location_id', '=', self.location_id.id))

            action['domain'] = domain
            action['display_name'] = _("Valuation Layers with Accounting Entries")
            action['context'] = {
                "to_date": self.inventory_datetime
            }

            return action

        # Comportamiento original si no es 'stock.valuation.layer'
        return super(StockQuantityHistoryExtended, self).open_at_date()



class ProductProduct(models.Model):
    _inherit = 'product.product'

    # location_ids = fields.Many2many(
    #     'stock.location', string='Ubicaciones',
    #     compute='_compute_location_ids', store=False
    # )

    # lot_ids = fields.Many2many(
    #     'stock.lot', string='Lotes Disponibles',
    #     compute='_compute_lot_ids', store=False
    # )

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

    # def _compute_location_ids(self):
    #     """Computa las ubicaciones donde está disponible el producto hasta la fecha consultada."""
    #     to_date = self.env.context.get('to_date')  # Fecha límite para consultar disponibilidad
    #     for product in self:
    #         domain = [('product_id', '=', product.id), ('quantity', '>', 0)]
    #         if to_date:
    #             domain.append(('in_date', '<=', to_date))  # Considerar solo movimientos hasta la fecha
    #         quants = self.env['stock.quant'].search(domain)
    #         product.location_ids = quants.mapped('location_id')

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

    account_move_id = fields.Many2one(
        'account.move', string='Asiento Contable', readonly=True
    )

    @api.depends('product_id', 'location_id')
    def _compute_account_move(self):
        for quant in self:
            valuation_layer = self.env['stock.valuation.layer'].search([
                ('product_id', '=', quant.product_id.id),
                ('location_id', '=', quant.location_id.id),
            ], limit=1)
            quant.account_move_id = valuation_layer.account_move_id if valuation_layer else False


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

    @api.depends('product_id', 'create_date')
    def _compute_location_id(self):
        """
        Determina todas las ubicaciones relevantes del producto basándose en cantidades disponibles.
        """
        for record in self:
            if record.product_id and record.create_date:
                quants = self.env['stock.quant'].search([
                    ('product_id', '=', record.product_id.id),
                    ('quantity', '>', 0),
                    ('in_date', '<=', record.create_date),
                    ('location_id.usage', 'in', ['internal', 'transit']),
                ])
                # Guardar todas las ubicaciones relevantes
                record.location_id = [(6, 0, quants.mapped('location_id').ids)]
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



class InventoryValuationWizard(models.TransientModel):
    _name = 'inventory.valuation.wizard'
    _description = 'Wizard para Generar Reporte de Valorización de Inventario'

    report_date = fields.Date(string='Fecha del Reporte', required=True, default=fields.Date.context_today)

    def generate_report(self):
        """
        Genera el reporte basado en la fecha seleccionada.
        """
        action = {
            'type': 'ir.actions.act_window',
            'name': _('Reporte de Valorización de Inventario'),
            'res_model': 'inventory.valuation.report',
            'view_mode': 'tree,form',
            'domain': [('valuation_date', '<=', self.report_date)],
            'context': {'default_report_date': self.report_date},
        }
        return action


class InventoryValuationReport(models.Model):
    _name = 'inventory.valuation.report'
    _auto = False
    _description = 'Reporte de Valorización de Inventario con Ubicaciones'

    product_id = fields.Many2one('product.product', string='Producto')
    location_id = fields.Many2one('stock.location', string='Ubicación')
    lot_id = fields.Many2one('stock.lot', string='Lote')
    quantity = fields.Float(string='Cantidad Disponible')
    reserved_quantity = fields.Float(string='Cantidad Reservada')
    unit_value = fields.Float(string='Precio Promedio Unitario')
    total_valuation = fields.Float(string='Valor Total Valorizado')
    layer_account_move_id = fields.Many2one('account.move', string='Asiento Contable (Valorización)')
    quant_account_move_id = fields.Many2one('account.move', string='Asiento Contable (Quant)')
    valuation_date = fields.Datetime(string='Fecha de Valorización')
    stock_move_date = fields.Datetime(string='Fecha del Movimiento')
    move_reference = fields.Char(string='Referencia del Movimiento')

    @api.model
    def _create_view(self):
        """
        Crear la vista SQL para el modelo `inventory.valuation.report`.
        """
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW inventory_valuation_report AS (
                SELECT
                    row_number() OVER () AS id,
                    quant.product_id AS product_id,
                    quant.location_id AS location_id,
                    quant.lot_id AS lot_id,
                    quant.quantity AS quantity,
                    quant.reserved_quantity AS reserved_quantity,
                    COALESCE(valuation.unit_cost, 0.0) AS unit_value,
                    COALESCE(valuation.value, 0.0) AS total_valuation,
                    valuation.account_move_id AS layer_account_move_id,
                    quant.account_move_id AS quant_account_move_id,
                    valuation.create_date AS valuation_date,
                    move.date AS stock_move_date,
                    move.reference AS move_reference
                FROM
                    stock_quant quant
                LEFT JOIN
                    stock_move move
                ON
                    quant.location_id = move.location_dest_id
                    AND quant.product_id = move.product_id
                LEFT JOIN
                    stock_valuation_layer valuation
                ON
                    move.id = valuation.stock_move_id
                    AND quant.product_id = valuation.product_id
                WHERE
                    quant.quantity > 0
                    AND quant.create_date <= CURRENT_DATE
                    AND (valuation.create_date IS NULL OR valuation.create_date <= CURRENT_DATE)
            );
        """)

    def init(self):
        self._create_view()
