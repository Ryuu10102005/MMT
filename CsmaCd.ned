simple Bus
{
    parameters:
        double maxPropDelay @unit(s) = default(5us);
        @display("i=device/bus;bgb=,,,,0");
    gates:
        input in[];
        output out[];
}

simple Node
{
    parameters:
        string protocol = default("csmacd");   // "csmacd" | "aloha" | "slotted"
        double G = default(0.5);
        double bitrate @unit(bps) = default(10Mbps);
        int frameBits = default(10000);
        int jamBits = default(32);
        int slotBits = default(512);
        int maxAttempts = default(16);
        int maxBackoffExp = default(10);
        int retxWindow = default(10);
        int queueLimit = default(10);
        bool deterministic = default(false);
        double firstArrival @unit(s) = default(1ms);

        @display("i=device/pc");

        @signal[delay](type=simtime_t);
        @signal[attempts](type=long);
        @signal[txStart](type=simtime_t);
        @signal[backoffSlots](type=long);
        @signal[backoffExponent](type=long);
        @statistic[txStart](source=txStart; record=vector);
        @statistic[backoffSlots](source=backoffSlots; record=vector);
        @statistic[backoffExponent](source=backoffExponent; record=vector);
        @statistic[delay](title="frame delay"; source=delay; record=mean,max,histogram);
        @statistic[attempts](title="transmissions per frame"; source=attempts; record=mean,max,histogram);
    gates:
        input in;
        output out;
}

network CsmaCdNet
{
    parameters:
        int numNodes = default(10);
    submodules:
        bus: Bus;
        node[numNodes]: Node;
    connections:
        for i=0..numNodes-1 {
            node[i].out --> bus.in++;
            bus.out++ --> node[i].in;
        }
}
