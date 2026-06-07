# Enhanced trading system with AutoHedge multi-agent approach

import json
from autohedge_agents import (
    director_agent, 
    quant_agent, 
    risk_agent, 
    execution_agent, 
    sentiment_agent,
    ALL_AGENTS
)

class AutoHedgeTradingSystem:
    def __init__(self):
        self.agents = ALL_AGENTS
        self.conversation_history = []
        
    def run_trading_cycle(self, market_task: str):
        """Run a complete trading cycle using the multi-agent approach"""
        print("Starting trading cycle with AutoHedge multi-agent approach...")
        
        # Run the director agent to get market thesis
        director_output = director_agent.run(market_task)
        self.conversation_history.append(f"Director: {director_output}")
        
        # Run the sentiment agent
        sentiment_task = f"Analyze market sentiment for the stocks mentioned in this thesis: {director_output}"
        sentiment_output = sentiment_agent.run(sentiment_task)
        self.conversation_history.append(f"Sentiment Agent: {sentiment_output}")
        
        # Run the quant agent
        quant_task = f"Provide quantitative analysis for the stocks mentioned in this thesis: {director_output}"
        quant_output = quant_agent.run(quant_task)
        self.conversation_history.get("Quant Agent: {quant_output}")
        
        # Run the risk agent
        risk_task = f"Provide risk assessment for this thesis: {director_output} with this quantitative analysis: {quant_output}"
        risk_output = risk_agent.run(risk_task)
        self.conversation_history.append(f"Risk Agent: {risk_output}")
        
        # Run the execution agent
        execution_task = f"Generate trade order for this thesis: {director_output} with this risk assessment: {risk_output}"
        execution_output = execution_agent.run(execution_task)
        self.conversation_history.append(f"Execution Agent: {execution_output}")
        
        print("Trading cycle completed with AutoHedge multi-agent approach")
        return self.conversation_history

    def get_latest_report(self):
        """Get a summary of the latest trading activities"""
        return "\n".join(self.conversation_history)

# Initialize the AutoHedge trading system
autohedge_system = AutoHedgeTradingSystem()
print("AutoHedge trading system initialized")