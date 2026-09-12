import 'package:flutter_test/flutter_test.dart';
import 'package:orca_app/core/agents/agent_registry.dart';

void main() {
  group('AgentRegistry Tests', () {
    test('Registry contains all 11 authoritative agents', () {
      expect(AgentRegistry.all.length, equals(11));

      final ids = AgentRegistry.all.map((a) => a.id).toSet();
      expect(ids.contains('data_validation'), isTrue);
      expect(ids.contains('gis_spatial'), isTrue);
      expect(ids.contains('ocean_analysis'), isTrue);
      expect(ids.contains('satellite_analysis'), isTrue);
      expect(ids.contains('weather_hazard'), isTrue);
      expect(ids.contains('map_synoptic'), isTrue);
      expect(ids.contains('marine_ecology'), isTrue);
      expect(ids.contains('fisheries_pfz'), isTrue);
      expect(ids.contains('anomaly_detection'), isTrue);
      expect(ids.contains('marine_risk'), isTrue);
      expect(ids.contains('orchestrator'), isTrue);
    });

    test('Deterministic vs LLM classifications match specification', () {
      final validation = AgentRegistry.findById('data_validation');
      expect(validation.isDeterministic, isTrue);

      final ocean = AgentRegistry.findById('ocean_analysis');
      expect(ocean.isLlm, isTrue);

      final risk = AgentRegistry.findById('marine_risk');
      expect(risk.isDeterministic, isTrue);
    });

    test('Unknown agent returns safe generic descriptor', () {
      final unknown = AgentRegistry.findById('custom_future_agent');
      expect(unknown.id, equals('custom_future_agent'));
      expect(unknown.name, equals('Custom Future Agent'));
      expect(unknown.emoji, equals('🤖'));
    });
  });
}
