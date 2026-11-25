//+------------------------------------------------------------------+
//| Bot ORB 5m - MetaTrader 5 (ouro e forex)                          |
//| Rompimento da faixa de abertura em velas de 5 minutos.            |
//| - Marca a faixa (padrão 08:00-08:15 de Nova York).                |
//| - Compra se uma vela de 5 min FECHA acima da máxima da faixa;     |
//|   vende se FECHA abaixo da mínima (pode desligar a venda).        |
//| - Stop no meio da faixa; alvo em 2R.                              |
//| - Lote calculado pelo risco (% do saldo) por trade.               |
//| - Até 3 trades por dia, rearme ao voltar para dentro da faixa,    |
//|   para no dia após 2 stops e zera no horário definido.            |
//| TESTE PRIMEIRO NO TESTADOR DE ESTRATÉGIA E EM CONTA DEMO.         |
//+------------------------------------------------------------------+
#property copyright "Ketlin"
#property version   "1.00"
#property description "Bot ORB 5m para ouro (XAUUSD) e forex. Teste em conta demo antes de usar."

#include <Trade\Trade.mqh>

//--- Horários (em horário de Nova York)
input int    InpFusoServidorNY   = 7;     // Hora do servidor menos hora de NY (geralmente 7)
input int    InpFaixaHora        = 8;     // Início da faixa: hora (NY)
input int    InpFaixaMinuto      = 0;     // Início da faixa: minuto (NY)
input int    InpFaixaDuracao     = 15;    // Duração da faixa em minutos (múltiplo de 5)
input int    InpEntradaFimHora   = 11;    // Última entrada: hora (NY)
input int    InpEntradaFimMinuto = 30;    // Última entrada: minuto (NY)
input int    InpZerarHora        = 16;    // Zerar posição: hora (NY)
input int    InpZerarMinuto      = 30;    // Zerar posição: minuto (NY)
//--- Regras do trade
input double InpAlvoR            = 2.0;   // Alvo em R (múltiplos do risco)
input int    InpMaxTrades        = 3;     // Máximo de trades por dia
input int    InpMaxStops         = 2;     // Parar no dia depois de X stops
input bool   InpPermitirVenda    = true;  // Permitir vendas
//--- Risco
input double InpRiscoPct         = 1.0;   // Risco por trade (% do saldo)
input bool   InpPularSeLoteMin   = true;  // Pular o trade se o lote mínimo arriscar mais que o permitido
input int    InpSpreadMaxPontos  = 0;     // Spread máximo em pontos (0 = sem limite)
input ulong  InpMagic            = 250519;// Número mágico (identifica as ordens do bot)

CTrade   trade;
datetime ultimaVela    = 0;
int      diaAtual      = 0;
datetime inicioDiaSrv  = 0;
double   orH = 0, orL = 0;
int      tradesHoje    = 0;
bool     armadoC = true, armadoV = true;

//--- Minutos do dia em NY a partir de um horário do servidor
int MinutoNY(datetime tServidor, MqlDateTime &d)
{
   TimeToStruct(tServidor - InpFusoServidorNY * 3600, d);
   return d.hour * 60 + d.min;
}

//--- Existe posição aberta deste bot neste símbolo?
bool TemPosicao()
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket > 0 && PositionGetString(POSITION_SYMBOL) == _Symbol &&
         (ulong)PositionGetInteger(POSITION_MAGIC) == InpMagic)
         return true;
   }
   return false;
}

//--- Fecha as posições deste bot
void ZerarPosicoes()
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket > 0 && PositionGetString(POSITION_SYMBOL) == _Symbol &&
         (ulong)PositionGetInteger(POSITION_MAGIC) == InpMagic)
         trade.PositionClose(ticket);
   }
}

//--- Conta os stops (trades fechados com prejuízo) do dia
int StopsHoje()
{
   if(inicioDiaSrv == 0 || !HistorySelect(inicioDiaSrv, TimeCurrent() + 60)) return 0;
   int n = 0;
   for(int i = HistoryDealsTotal() - 1; i >= 0; i--)
   {
      ulong d = HistoryDealGetTicket(i);
      if(d == 0) continue;
      if(HistoryDealGetString(d, DEAL_SYMBOL) != _Symbol) continue;
      if((ulong)HistoryDealGetInteger(d, DEAL_MAGIC) != InpMagic) continue;
      if(HistoryDealGetInteger(d, DEAL_ENTRY) != DEAL_ENTRY_OUT) continue;
      double res = HistoryDealGetDouble(d, DEAL_PROFIT) + HistoryDealGetDouble(d, DEAL_COMMISSION) + HistoryDealGetDouble(d, DEAL_SWAP);
      if(res < 0) n++;
   }
   return n;
}

//--- Lote pelo risco; devolve 0 se não for possível
double CalcularLote(double distanciaStop)
{
   double tickVal  = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE_LOSS);
   double tickSize = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   double passo    = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   double minimo   = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double maximo   = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   if(tickVal <= 0 || tickSize <= 0 || passo <= 0 || distanciaStop <= 0) return 0;

   double perdaPorLote = distanciaStop / tickSize * tickVal;
   double riscoUSD     = AccountInfoDouble(ACCOUNT_BALANCE) * InpRiscoPct / 100.0;
   double lote         = MathFloor((riscoUSD / perdaPorLote) / passo) * passo;

   if(lote < minimo)
   {
      if(InpPularSeLoteMin)
      {
         PrintFormat("Trade pulado: o lote mínimo (%.2f) arriscaria US$ %.2f, acima de US$ %.2f (%.1f%% do saldo).",
                     minimo, minimo * perdaPorLote, riscoUSD, InpRiscoPct);
         return 0;
      }
      lote = minimo;
   }
   return MathMin(lote, maximo);
}

//--- Desenha uma linha horizontal no gráfico
void Linha(string nome, double preco, color cor, ENUM_LINE_STYLE estilo)
{
   if(ObjectFind(0, nome) < 0) ObjectCreate(0, nome, OBJ_HLINE, 0, 0, preco);
   ObjectSetDouble(0, nome, OBJPROP_PRICE, preco);
   ObjectSetInteger(0, nome, OBJPROP_COLOR, cor);
   ObjectSetInteger(0, nome, OBJPROP_STYLE, estilo);
   ObjectSetInteger(0, nome, OBJPROP_WIDTH, 1);
}

int OnInit()
{
   trade.SetExpertMagicNumber(InpMagic);
   trade.SetTypeFillingBySymbol(_Symbol);
   if(InpFaixaDuracao < 5 || InpFaixaDuracao % 5 != 0)
   {
      Print("A duração da faixa precisa ser múltiplo de 5 minutos.");
      return INIT_PARAMETERS_INCORRECT;
   }
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   ObjectDelete(0, "ORB_max");
   ObjectDelete(0, "ORB_min");
   ObjectDelete(0, "ORB_meio");
   Comment("");
}

void OnTick()
{
   MqlDateTime agora;
   int minAgora   = MinutoNY(TimeCurrent(), agora);
   int minZerar   = InpZerarHora * 60 + InpZerarMinuto;

   //--- Zerar no horário
   if(minAgora >= minZerar && TemPosicao())
      ZerarPosicoes();

   //--- Trabalha só no fechamento de cada vela de 5 minutos
   datetime velaAtual = iTime(_Symbol, PERIOD_M5, 0);
   if(velaAtual == 0 || velaAtual == ultimaVela) return;
   ultimaVela = velaAtual;

   datetime t1 = iTime(_Symbol, PERIOD_M5, 1);
   double   h1 = iHigh(_Symbol, PERIOD_M5, 1);
   double   l1 = iLow(_Symbol, PERIOD_M5, 1);
   double   c1 = iClose(_Symbol, PERIOD_M5, 1);
   if(t1 == 0) return;

   MqlDateTime d;
   int minVela = MinutoNY(t1, d);
   int chaveDia = d.year * 10000 + d.mon * 100 + d.day;

   //--- Novo dia (em NY): zera tudo
   if(chaveDia != diaAtual)
   {
      diaAtual     = chaveDia;
      inicioDiaSrv = t1 - minVela * 60;
      orH = 0; orL = 0;
      tradesHoje = 0;
      armadoC = true; armadoV = true;
   }

   int iniFaixa = InpFaixaHora * 60 + InpFaixaMinuto;
   int fimFaixa = iniFaixa + InpFaixaDuracao;
   int fimEntr  = InpEntradaFimHora * 60 + InpEntradaFimMinuto;

   //--- Monta a faixa de abertura
   if(minVela >= iniFaixa && minVela < fimFaixa)
   {
      orH = (orH == 0) ? h1 : MathMax(orH, h1);
      orL = (orL == 0) ? l1 : MathMin(orL, l1);
   }

   bool pronta = (orH > 0 && minVela >= fimFaixa);
   double meio = (orH + orL) / 2.0;
   int stops   = StopsHoje();

   if(pronta)
   {
      Linha("ORB_max",  orH,  clrDodgerBlue, STYLE_SOLID);
      Linha("ORB_min",  orL,  clrGray,       STYLE_DASH);
      Linha("ORB_meio", meio, clrRed,        STYLE_DOT);

      //--- Rearme: precisa voltar para dentro da faixa
      if(c1 <= orH) armadoC = true;
      if(c1 >= orL) armadoV = true;
   }

   Comment(StringFormat("Bot ORB 5m | faixa %s | máx %s | mín %s | trades hoje %d/%d | stops %d/%d",
           pronta ? "pronta" : "aguardando",
           DoubleToString(orH, _Digits), DoubleToString(orL, _Digits),
           tradesHoje, InpMaxTrades, stops, InpMaxStops));

   if(!pronta || minVela >= fimEntr || tradesHoje >= InpMaxTrades || stops >= InpMaxStops || TemPosicao())
      return;

   if(InpSpreadMaxPontos > 0 && SymbolInfoInteger(_Symbol, SYMBOL_SPREAD) > InpSpreadMaxPontos)
   {
      Print("Entrada ignorada: spread acima do máximo.");
      return;
   }

   double ask   = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bid   = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double nivel = SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL) * _Point;

   //--- Compra
   if(armadoC && c1 > orH)
   {
      double sl = NormalizeDouble(meio, _Digits);
      double r  = ask - sl;
      if(r > nivel && r > 0)
      {
         double tp   = NormalizeDouble(ask + InpAlvoR * r, _Digits);
         double lote = CalcularLote(r);
         if(lote > 0 && trade.Buy(lote, _Symbol, 0, sl, tp, "ORB compra"))
         {
            tradesHoje++;
            armadoC = false;
         }
      }
      return;
   }

   //--- Venda
   if(InpPermitirVenda && armadoV && c1 < orL)
   {
      double sl = NormalizeDouble(meio, _Digits);
      double r  = sl - bid;
      if(r > nivel && r > 0)
      {
         double tp   = NormalizeDouble(bid - InpAlvoR * r, _Digits);
         double lote = CalcularLote(r);
         if(lote > 0 && trade.Sell(lote, _Symbol, 0, sl, tp, "ORB venda"))
         {
            tradesHoje++;
            armadoV = false;
         }
      }
   }
}
//+------------------------------------------------------------------+
