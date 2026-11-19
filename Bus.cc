#include "Node.h"
#include <cmath>
#include <map>

using namespace omnetpp;

class Bus : public cSimpleModule
{
  protected:
    simtime_t maxProp;
    struct Transmission {
        bool ended = false;
        bool collided = false;
        simtime_t end;
        cMessage *result = nullptr;
    };
    using Key = std::pair<int, long>;
    std::map<Key, Transmission> transmissions;
    simtime_t delay(int i, int j) const;
    virtual void initialize() override;
    virtual void handleMessage(cMessage *msg) override;
  public:
    virtual ~Bus();
};

Define_Module(Bus);

void Bus::initialize()
{
    double propagation = par("maxPropDelay").doubleValue();
    if (!std::isfinite(propagation) || propagation < 0)
        throw cRuntimeError("maxPropDelay must be finite and nonnegative");
    int numNodes = getParentModule()->par("numNodes");
    if (numNodes < 1 || gateSize("in") != numNodes || gateSize("out") != numNodes)
        throw cRuntimeError("The bus requires at least one node and one gate pair per node");
    maxProp = SimTime(propagation);
}

// Shared physical rule: intervals i,j collide anywhere on the linear bus iff
// s_i < e_j+d_ij and s_j < e_i+d_ij. At a new START, prior s_j <= s_i,
// so only the prior trailing edge needs checking. Keep ended intervals until
// maxProp has drained, then return the same ideal verdict to every MAC.
Bus::~Bus()
{
    for (auto& entry : transmissions) cancelAndDelete(entry.second.result);
}

simtime_t Bus::delay(int i, int j) const
{
    int n = gateSize("out");
    return n > 1 ? maxProp * (std::fabs(double(i - j)) / (n - 1)) : SIMTIME_ZERO;
}

void Bus::handleMessage(cMessage *msg)
{
    if (msg->isSelfMessage()) {
        int src = msg->par("src").longValue();
        Key key(src, msg->par("attemptId").longValue());
        auto entry = transmissions.find(key);
        if (entry == transmissions.end() || entry->second.result != msg)
            throw cRuntimeError("Unknown channel result");
        msg->addPar("collided").setBoolValue(entry->second.collided);
        entry->second.result = nullptr;
        transmissions.erase(entry);
        send(msg, "out", src);
        return;
    }

    int src = msg->getArrivalGate()->getIndex();
    Key key(src, msg->par("attemptId").longValue());
    if (msg->getKind() == SIG_START) {
        auto inserted = transmissions.emplace(key, Transmission{});
        if (!inserted.second) throw cRuntimeError("Duplicate transmission START");
        for (auto& other : transmissions) {
            if (other.first.first == src) continue;
            if (!other.second.ended || simTime() < other.second.end + delay(src, other.first.first)) {
                inserted.first->second.collided = true;
                other.second.collided = true;
            }
        }
    }
    else if (msg->getKind() == SIG_END) {
        auto entry = transmissions.find(key);
        if (entry == transmissions.end() || entry->second.ended)
            throw cRuntimeError("Unbalanced transmission END");
        entry->second.ended = true;
        entry->second.end = simTime();
        auto *result = new cMessage("channelResult", SIG_RESULT);
        result->addPar("src").setLongValue(src);
        result->addPar("attemptId").setLongValue(key.second);
        // START/END and slot starts at this timestamp precede verdicts.
        result->setSchedulingPriority(3);
        entry->second.result = result;
        scheduleAt(simTime() + maxProp, result);
    }
    else throw cRuntimeError("Unknown bus signal");

    for (int j = 0; j < gateSize("out"); j++)
        if (j != src) sendDelayed(msg->dup(), delay(src, j), "out", j);
    delete msg;
}
