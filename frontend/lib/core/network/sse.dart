import 'dart:async';
import 'dart:convert';

/// Parsed Server-Sent Event.
class SseEvent {
  final String event;
  final String data;
  final String? id;
  final int? retry;

  const SseEvent({
    required this.event,
    required this.data,
    this.id,
    this.retry,
  });

  dynamic get jsonData {
    try {
      return jsonDecode(data);
    } catch (_) {
      return data;
    }
  }

  @override
  String toString() => 'SseEvent(event: $event, data: $data)';
}

/// Incremental SSE decoder. Event fields deliberately survive arbitrary
/// network chunk boundaries until the terminating blank line arrives.
class SseDecoder extends StreamTransformerBase<String, SseEvent> {
  const SseDecoder();

  @override
  Stream<SseEvent> bind(Stream<String> stream) {
    return Stream<SseEvent>.eventTransformed(
      stream,
      (EventSink<SseEvent> sink) => _SseEventSink(sink),
    );
  }
}

class _SseEventSink implements EventSink<String> {
  final EventSink<SseEvent> _outputSink;
  String _buffer = '';
  String _event = 'message';
  final List<String> _dataLines = <String>[];
  String? _id;
  int? _retry;

  _SseEventSink(this._outputSink);

  @override
  void add(String chunk) {
    _buffer += chunk;
    while (true) {
      final match = RegExp(r'\r\n|\r|\n').firstMatch(_buffer);
      if (match == null) break;
      final line = _buffer.substring(0, match.start);
      _buffer = _buffer.substring(match.end);
      _consumeLine(line);
    }
  }

  void _consumeLine(String line) {
    if (line.isEmpty) {
      _dispatch();
      return;
    }
    if (line.startsWith(':')) return; // heartbeat comment

    final colon = line.indexOf(':');
    final field = colon < 0 ? line : line.substring(0, colon);
    var value = colon < 0 ? '' : line.substring(colon + 1);
    if (value.startsWith(' ')) value = value.substring(1);

    switch (field) {
      case 'event':
        _event = value.isEmpty ? 'message' : value;
        break;
      case 'data':
        _dataLines.add(value);
        break;
      case 'id':
        if (!value.contains('\u0000')) _id = value;
        break;
      case 'retry':
        _retry = int.tryParse(value);
        break;
    }
  }

  void _dispatch() {
    if (_dataLines.isNotEmpty) {
      _outputSink.add(SseEvent(
        event: _event,
        data: _dataLines.join('\n'),
        id: _id,
        retry: _retry,
      ));
    }
    _event = 'message';
    _dataLines.clear();
    _retry = null;
    // SSE id persists across events until a later id field replaces it.
  }

  @override
  void addError(Object error, [StackTrace? stackTrace]) {
    _outputSink.addError(error, stackTrace);
  }

  @override
  void close() {
    if (_buffer.isNotEmpty) _consumeLine(_buffer);
    _dispatch();
    _outputSink.close();
  }
}
