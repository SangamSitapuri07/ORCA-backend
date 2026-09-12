import 'package:flutter_test/flutter_test.dart';
import 'package:orca_app/core/cache/staleness.dart';
import 'package:orca_app/features/agents/data/dto/reason_dto.dart';

void main() {
  group('ReasonDto & Agents Parsing Tests', () {
    test('Parses multi-agent reasoning trace with evidence and orchestrator synthesis', () {
      final jsonMap = {
        'overall_risk': 'MODERATE',
        'verdict': 'caution',
        'data_coverage': {
          'known': 7,
          'total': 8,
          'sources_failed': ['ESA OC-CCI (Cloud-masked)']
        },
        'agents': [
          {
            'agent_id': 'data_validation',
            'name': 'Data Validation',
            'emoji': '✅',
            'class': 'DETERMINISTIC',
            'status': 'completed',
            'duration_ms': 42,
            'verdict': 'good',
            'summary': '7 of 8 datasets passed QC gates.',
            'evidence': ['Open-Meteo range: OK'],
            'warnings': []
          },
          {
            'agent_id': 'marine_risk',
            'name': 'Marine Risk',
            'emoji': '🚨',
            'class': 'DETERMINISTIC',
            'status': 'completed',
            'duration_ms': 40,
            'verdict': 'caution',
            'summary': 'Worst case fold triggered on wave height 2.6m.',
            'evidence': ['Wave: CAUTION'],
            'warnings': ['Caution: waves > 2.5m']
          }
        ],
        'orchestrator_synthesis': {
          'headline': 'Safe for day transit within 15 km coast.',
          'recommendation': 'Return by 15:30 IST.',
          'trace_owner': '🧠 Orchestrator Agent (SIH26176)',
          'timestamp': '2026-09-12T08:30:00Z'
        }
      };

      final dto = ReasonDto.fromJson(jsonMap);
      final staleness = StalenessInfo.fromDateTime(DateTime.now());
      final entity = dto.toEntity(staleness);

      expect(entity.overallRisk, equals('MODERATE'));
      expect(entity.agents.length, equals(2));
      expect(entity.agents.first.agentId, equals('data_validation'));
      expect(entity.agents.first.evidence.first, equals('Open-Meteo range: OK'));
      expect(entity.orchestratorSynthesis.headline, contains('Safe for day transit'));
    });
  });
}
