package com.ssafy.backend.mqtt.config;

import com.ssafy.backend.mqtt.position.MqttPositionMessageHandler;
import org.eclipse.paho.client.mqttv3.MqttConnectOptions;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.core.MessageProducer;
import org.springframework.integration.mqtt.core.DefaultMqttPahoClientFactory;
import org.springframework.integration.mqtt.core.MqttPahoClientFactory;
import org.springframework.integration.mqtt.inbound.MqttPahoMessageDrivenChannelAdapter;
import org.springframework.integration.mqtt.support.DefaultPahoMessageConverter;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageHandler;

@Configuration
@EnableIntegration
@EnableConfigurationProperties(MqttProperties.class)
@ConditionalOnProperty(prefix = "mqtt", name = "enabled", havingValue = "true")
public class MqttConfig {

	@Bean
	public MqttPahoClientFactory mqttClientFactory(MqttProperties properties) {
		MqttConnectOptions options = new MqttConnectOptions();
		options.setServerURIs(new String[]{properties.getBrokerUrl()});
		options.setAutomaticReconnect(true);
		options.setCleanSession(true);

		DefaultMqttPahoClientFactory factory = new DefaultMqttPahoClientFactory();
		factory.setConnectionOptions(options);
		return factory;
	}

	@Bean
	public MessageChannel mqttInputChannel() {
		return new DirectChannel();
	}

	@Bean
	public MessageProducer mqttInbound(
		MqttProperties properties,
		MqttPahoClientFactory mqttClientFactory,
		MessageChannel mqttInputChannel
	) {
		MqttPahoMessageDrivenChannelAdapter adapter =
			new MqttPahoMessageDrivenChannelAdapter(
				properties.getClientId(),
				mqttClientFactory,
				properties.getPositionTopic()
			);
		adapter.setQos(properties.getQos());
		adapter.setConverter(new DefaultPahoMessageConverter());
		adapter.setOutputChannel(mqttInputChannel);
		return adapter;
	}

	@Bean
	@ServiceActivator(inputChannel = "mqttInputChannel")
	public MessageHandler mqttPositionHandler(MqttPositionMessageHandler handler) {
		return handler::handle;
	}
}
