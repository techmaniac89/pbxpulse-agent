import java.lang.reflect.Array;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.time.Instant;
import java.util.IdentityHashMap;
import java.util.LinkedHashMap;
import java.util.Map;

/** Reflection-only Cisco JTAPI poller. The Cisco jar is supplied by the CUCM administrator. */
public final class PBXSenseJtapiBridge {
  private static final Map<Object, Long> STARTED = new IdentityHashMap<>();

  public static void main(String[] args) throws Exception {
    String host = required("PBXSENSE_JTAPI_HOST");
    String username = required("PBXSENSE_JTAPI_USERNAME");
    String password = required("PBXSENSE_JTAPI_PASSWORD");
    long pollMs = Long.parseLong(System.getenv().getOrDefault("PBXSENSE_JTAPI_POLL_MS", "1000"));
    Class<?> factory = Class.forName("javax.telephony.JtapiPeerFactory");
    Object peer = factory.getMethod("getJtapiPeer", String.class).invoke(null, new Object[] {null});
    Object provider = invoke(peer, "getProvider", host + ";login=" + username + ";passwd=" + password);
    waitForProvider(provider);
    while (true) {
      System.out.println(snapshot(provider));
      System.out.flush();
      Thread.sleep(Math.max(250, pollMs));
    }
  }

  private static String snapshot(Object provider) throws Exception {
    Map<Object, CallView> calls = new IdentityHashMap<>();
    for (Object address : array(invoke(provider, "getAddresses"))) {
      String local = text(invoke(address, "getName"));
      for (Object connection : array(optional(address, "getConnections"))) {
        Object call = optional(connection, "getCall");
        if (call == null || !isActive(call)) continue;
        CallView view = calls.computeIfAbsent(call, key -> new CallView(key));
        view.observeLocal(local);
      }
    }
    long now = Instant.now().getEpochSecond();
    StringBuilder out = new StringBuilder("{\"timestamp\":").append(now).append(",\"calls\":[");
    boolean first = true;
    for (Map.Entry<Object, CallView> entry : calls.entrySet()) {
      if (!first) out.append(',');
      first = false;
      long started = STARTED.computeIfAbsent(entry.getKey(), key -> now);
      out.append(entry.getValue().json(now - started));
    }
    STARTED.keySet().retainAll(calls.keySet());
    return out.append("]}").toString();
  }

  private static boolean isActive(Object call) {
    try {
      int state = ((Number) invoke(call, "getState")).intValue();
      return state == constant(call.getClass(), "ACTIVE", state);
    } catch (Exception ignored) {
      return true;
    }
  }

  private static void waitForProvider(Object provider) throws Exception {
    long deadline = System.currentTimeMillis() + 30000;
    while (System.currentTimeMillis() < deadline) {
      int state = ((Number) invoke(provider, "getState")).intValue();
      int inService = constant(provider.getClass(), "IN_SERVICE", state);
      if (state == inService) return;
      Thread.sleep(250);
    }
    throw new IllegalStateException("CUCM JTAPI provider did not enter service within 30 seconds");
  }

  private static int constant(Class<?> type, String name, int fallback) {
    try { Field field = type.getField(name); return field.getInt(null); } catch (Exception ignored) {}
    for (Class<?> iface : type.getInterfaces()) {
      int value = constant(iface, name, Integer.MIN_VALUE);
      if (value != Integer.MIN_VALUE) return value;
    }
    Class<?> parent = type.getSuperclass();
    return parent == null ? fallback : constant(parent, name, fallback);
  }

  private static String callId(Object call) {
    for (String method : new String[] {"getGlobalCallID", "getCallID"}) {
      Object value = optional(call, method);
      if (value != null) return text(value);
    }
    return Integer.toHexString(System.identityHashCode(call));
  }

  private static Object invoke(Object target, String name, Object... args) throws Exception {
    for (Method method : target.getClass().getMethods()) {
      if (method.getName().equals(name) && method.getParameterCount() == args.length) {
        return method.invoke(target, args);
      }
    }
    throw new NoSuchMethodException(name);
  }

  private static Object optional(Object target, String name) {
    if (target == null) return null;
    try { return invoke(target, name); } catch (Exception ignored) { return null; }
  }

  private static Object[] array(Object value) {
    if (value == null || !value.getClass().isArray()) return new Object[0];
    int length = Array.getLength(value);
    Object[] result = new Object[length];
    for (int i = 0; i < length; i++) result[i] = Array.get(value, i);
    return result;
  }

  private static String required(String name) {
    String value = System.getenv(name);
    if (blank(value)) throw new IllegalArgumentException(name + " is required");
    return value;
  }

  private static String text(Object value) { return value == null ? "" : value.toString().trim(); }
  private static boolean blank(String value) { return value == null || value.trim().isEmpty(); }
  private static String quote(String value) {
    return "\"" + value.replace("\\", "\\\\").replace("\"", "\\\"")
      .replace("\n", "\\n").replace("\r", "\\r") + "\"";
  }

  private static final class CallView {
    final String id;
    final Map<String, Boolean> parties = new LinkedHashMap<>();
    String caller = "";
    String destination = "";
    String extension = "";
    boolean ringing;
    CallView(Object call) {
      this.id = callId(call);
      this.caller = addressName(optional(call, "getCallingAddress"));
      this.destination = addressName(optional(call, "getCalledAddress"));
      if (blank(this.destination)) this.destination = addressName(optional(call, "getCurrentCalledAddress"));
      for (Object connection : array(optional(call, "getConnections"))) observeConnection(connection);
    }
    void observeLocal(String local) {
      if (!blank(local)) {
        parties.put(local, true);
        if (blank(extension)) extension = local;
      }
    }
    void observeConnection(Object connection) {
      Object address = optional(connection, "getAddress");
      String name = addressName(address);
      if (!blank(name)) parties.put(name, true);
      Object stateValue = optional(connection, "getState");
      if (stateValue instanceof Number) {
        int state = ((Number) stateValue).intValue();
        ringing |= state == constant(connection.getClass(), "ALERTING", Integer.MIN_VALUE);
      }
    }
    String json(long duration) {
      String[] values = parties.keySet().toArray(new String[0]);
      String shownCaller = blank(caller) && values.length > 0 ? values[0] : caller;
      String shownDestination = blank(destination) && values.length > 1 ? values[1] : destination;
      String shownExtension = blank(extension) ? shownCaller : extension;
      return "{\"id\":" + quote(id) + ",\"caller\":" + quote(shownCaller)
        + ",\"destination\":" + quote(shownDestination) + ",\"extension\":" + quote(shownExtension)
        + ",\"state\":" + quote(ringing ? "Ringing" : "Up")
        + ",\"duration\":" + quote(Long.toString(duration)) + "}";
    }
  }

  private static String addressName(Object address) {
    if (address == null) return "";
    Object name = optional(address, "getName");
    return name == null ? text(address) : text(name);
  }
}
