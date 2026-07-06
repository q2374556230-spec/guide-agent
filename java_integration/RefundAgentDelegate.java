package com.example;

import org.camunda.bpm.engine.delegate.DelegateExecution;
import org.camunda.bpm.engine.delegate.JavaDelegate;

/**
 * 方式三:用 Java BPMN 引擎(Camunda/Flowable/Activiti)运行 aftersale.bpmn。
 * 把流程里的"智能步骤"做成 ServiceTask,委托给本类去调用 Agent 服务。
 *
 * 在 aftersale.bpmn 对应的 ServiceTask 上配置(Camunda):
 *   <bpmn:serviceTask id="Task_AutoRefund" name="自动发起退款"
 *                     camunda:class="com.example.RefundAgentDelegate"/>
 * 这样:Camunda(Java)负责流程编排与治理,智能/对话/RAG 等步骤交给 Agent 服务。
 */
public class RefundAgentDelegate implements JavaDelegate {

    @Override
    public void execute(DelegateExecution execution) throws Exception {
        String orderId = (String) execution.getVariable("orderId");
        // 调用 Agent 服务完成该节点(也可直接调你的退款微服务)
        String result = AgentClient.chat("对订单" + orderId + "申请售后退款", "u001");
        execution.setVariable("agentResult", result);
    }
}
