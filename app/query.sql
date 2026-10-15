-- Consulta original de upgrades/downgrades, adaptada:
--  * período parametrizado (inicio inclusive, fim exclusivo) no lugar do mês fixo
--  * lista de empresas excluídas injetada pelo Python no lugar do marcador de excluídas
--  * sem GROUP BY final (um registro por pagamento, para não perder mudanças
--    de meses diferentes da mesma empresa e para evitar erro de ONLY_FULL_GROUP_BY)
--  * celular vem de uma subconsulta (1 por empresa) para não duplicar linhas
--  * ATENÇÃO: não escreva o símbolo de porcentagem em comentários deste arquivo;
--    o driver o interpreta como parâmetro. No LIKE ele já aparece duplicado de propósito.
with plano_atual as (
	select
		ep.id,
        e.modalidade,
        e.empresa_indicacao_id,
        e.tipo_cobranca,
        ep.razao_social,
		ep.empresa_id,
		ep.nome_plano,
        case
        	when e.modalidade = 'ERP' then
				case
					when ep.nome_plano = 'Bronze' then 1
					when ep.nome_plano = 'Prata' then 2
					when ep.nome_plano = 'Ouro' then 3
					when ep.nome_plano = 'Platina' then 4
				end
			else
				case
					when ep.nome_plano = 'Bronze' then 1
					when ep.nome_plano = 'Prata' then 2
					when ep.nome_plano = 'Ouro' then 3
					when ep.nome_plano = 'Platina' then 4
					when ep.nome_plano = 'Plus' then 5
					when ep.nome_plano = 'Essencial' then 6
					when ep.nome_plano = 'Profissional' then 7
					when ep.nome_plano = 'Intermediário' then 8
					when ep.nome_plano = 'Master' then 9
				end
		end as peso_plano,
		ep.duracao,
        case
        	when ep.duracao = 'M' then 1
            when ep.duracao = 'T' then 2
            when ep.duracao = 'S' then 3
            when ep.duracao = 'A' then 4
		end as peso_duracao,
		case
			when ep.plano_agregado > ep.valor then ep.plano_agregado
			else ep.valor
		end as valor,
		ep.data_vencimento,
		ep.pago_em,
        ep.nome_usuario,
        ep.telefone,
        l.celular,
        ep.email
	from
		empresas_planos ep
		join empresas e on ep.empresa_id = e.id
        left join (
			select empresa_id, min(nullif(celular, '')) as celular
			from lojas
			group by empresa_id
		) l on ep.empresa_id = l.empresa_id
	where
		ep.plano_id <> 1
        and e.empresa_indicacao_id = 1
        and e.modalidade = 'ERP'
        and e.tipo_cobranca = 'E'
		and ep.valor > 5
		and ep.nota_fiscal_servico_id is not null
		and ep.pago_em >= %(inicio)s
		and ep.pago_em < %(fim)s
		and ep.nome_plano not like '%% recursos'
		and ep.pago_em > e.ativou_em
		and ep.empresa_id not in ({{EXCLUIDOS}})
),

plano_anterior_ranqueado as (
	select
		pa.id as id_plano_atual,
		ep.id as id_plano_anterior,
		ep.empresa_id,
        e.modalidade,
        e.empresa_indicacao_id,
        e.tipo_cobranca,
		ep.nome_plano,
        case
        	when e.modalidade = 'ERP' then
				case
					when ep.nome_plano = 'Bronze' then 1
					when ep.nome_plano = 'Prata' then 2
					when ep.nome_plano = 'Ouro' then 3
					when ep.nome_plano = 'Platina' then 4
				end
			else
				case
					when ep.nome_plano = 'Bronze' then 1
					when ep.nome_plano = 'Prata' then 2
					when ep.nome_plano = 'Ouro' then 3
					when ep.nome_plano = 'Platina' then 4
					when ep.nome_plano = 'Plus' then 5
					when ep.nome_plano = 'Essencial' then 6
					when ep.nome_plano = 'Profissional' then 7
					when ep.nome_plano = 'Intermediário' then 8
					when ep.nome_plano = 'Master' then 9
				end
		end as peso_plano,
		ep.duracao,
        case
        	when ep.duracao = 'M' then 1
            when ep.duracao = 'T' then 2
            when ep.duracao = 'S' then 3
            when ep.duracao = 'A' then 4
		end as peso_duracao,
		case
			when ep.plano_agregado > ep.valor then ep.plano_agregado
			else ep.valor
		end as valor,
		ep.data_vencimento,
		ep.pago_em,
		row_number() over (
			partition by pa.id
			order by ep.pago_em desc, ep.id desc
		) as rn
	from
		plano_atual pa
		join empresas_planos ep on ep.empresa_id = pa.empresa_id
		join empresas e on ep.empresa_id = e.id
	where
		ep.plano_id <> 1
		and ep.valor > 5
		and ep.nota_fiscal_servico_id is not null
		and ep.nome_plano not like '%% recursos'
		and ep.pago_em is not null
		and ep.pago_em > e.ativou_em
		and (
			ep.pago_em < pa.pago_em
			or (
				ep.pago_em = pa.pago_em
				and ep.id < pa.id
			)
		)
		and ep.empresa_id not in ({{EXCLUIDOS}})
),

plano_anterior as (
	select
		id_plano_atual,
		id_plano_anterior as id,
		empresa_id,
		nome_plano,
        peso_plano,
		duracao,
        peso_duracao,
		valor,
		data_vencimento,
		pago_em
	from
		plano_anterior_ranqueado
	where
		rn = 1
)

select
	pa.id as id_plano_atual,
	pa.empresa_id,
    pa.razao_social,
	pant.nome_plano as plano_anterior,
	pa.nome_plano as plano_atual,
    case
    	when pa.peso_plano > pant.peso_plano then 'Upgrade'
        when pa.peso_plano < pant.peso_plano then 'Downgrade'
        else 'Sem alteração'
	end as alteracao_plano,
	pant.duracao as duracao_anterior,
	pa.duracao as duracao_atual,
    case
    	when pa.peso_duracao > pant.peso_duracao then 'Upgrade'
        when pa.peso_duracao < pant.peso_duracao then 'Downgrade'
        else 'Sem alteração'
	end as alteracao_duracao,
	pant.valor as valor_anterior,
	pa.valor as valor_atual,
    round(case
			when pa.peso_plano <> pant.peso_plano
				or pa.peso_duracao <> pant.peso_duracao
			then pa.valor - pant.valor
			else 0
		end, 2) as diferenca_valor,
	pant.pago_em as pagamento_anterior,
	pa.pago_em as pagamento_atual,
    pa.nome_usuario,
    pa.telefone,
    pa.celular,
    pa.email
from
	plano_atual pa
	left join plano_anterior pant on pant.id_plano_atual = pa.id
where
	pa.peso_plano <> pant.peso_plano
	or pa.peso_duracao <> pant.peso_duracao
order by
	pa.pago_em desc;
