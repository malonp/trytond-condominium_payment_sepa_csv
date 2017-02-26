##############################################################################
#
#    GNU Condo: The Free Management Condominium System
#    Copyright (C) 2016- M. Alonso <port02.server@gmail.com>
#
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

import unicodecsv
from cStringIO import StringIO
from decimal import Decimal, DecimalException

from trytond.pool import PoolMeta, Pool
from trytond.model import ModelView, fields, dualmethod
from trytond.pyson import Eval, Bool


__all__ = ['CondoPaymentGroup']


class CondoPaymentGroup:
    __metaclass__ = PoolMeta
    __name__ = 'condo.payment.group'

    message = fields.Text('Message',
        states={
            'readonly': Bool(Eval('readonly'))
            },
        depends=['readonly'])

    @classmethod
    def __setup__(cls):
        super(CondoPaymentGroup, cls).__setup__()
        t = cls.__table__()
        cls._buttons.update({
                'generate_fees': {
                    'invisible': Bool(Eval('readonly'))},
                })

    @dualmethod
    @ModelView.button
    def generate_fees(cls, groups, _save=True):
        pool = Pool()

        CondoParties = pool.get('condo.party')
        CondoPayments = pool.get('condo.payment')

        for group in groups:
            condoparties = CondoParties.search([('unit.company', '=', group.company),
                ('sepa_mandate', '!=', None),
                ('sepa_mandate.state', 'not in', ['draft', 'canceled']),
                ('sepa_mandate.account_number', '!=', None),
                ], order=[('unit.name', 'ASC'),])

            if group.message:
                message = group.message.encode('utf-8')
                f = StringIO(message)
                r = unicodecsv.reader(f, delimiter=';', encoding='utf-8')
                information = list(map(tuple, r))

            #delete payments of this group with state='draft'
            CondoPayments.delete([p for p in group.payments if p.state=='draft'])

            for condoparty in condoparties:
                if CondoPayments.search_count([
                               ('group', '=', group),
                               ('unit', '=', condoparty.unit),
                               ('party', '=', condoparty.party)])==0:
                    condopayment = CondoPayments(
                                      group = group,
                                      unit = condoparty.unit,
                                      #Set the condoparty as the party
                                      #(instead the debtor of the mandate condoparty.sepa_mandate.party)
                                      party = condoparty.party,
                                      currency = group.company.currency,
                                      sepa_mandate = condoparty.sepa_mandate,
                                      type = condoparty.sepa_mandate.type,
                                      date = group.date,
                                      sepa_end_to_end_id = condoparty.unit.name)
                    #Read rest fields from message file
                    if group.message and len(information):
                        concepts = [x for x in information if x[0]==condoparty.unit.name]
                        for concept in concepts:
                            if ((len(concept)==4 and (condoparty.role==concept[3] if bool(concept[3]) else not bool(condoparty.role)))
                                or (len(concept)==3 and len(concepts)==1)):
                                    try:
                                        condopayment.amount = Decimal(concept[1].replace(",", "."))
                                        condopayment.description = concept[2]
                                    except DecimalException:
                                        cls.raise_user_error('Amount of fee for unit "%s" is invalid!',
                                                              condoparty.unit.name)

                                    if condopayment.amount<=0:
                                        cls.raise_user_warning('warn_invalid_amount.%d.%d' % (group.id, condoparty.id),
                                            'Amount of fee for unit "%s" must be bigger than zero!', condoparty.unit.name)

                                    #Consider only condopayments included in group.message
                                    group.payments += (condopayment,)
        if _save:
            cls.save(groups)
