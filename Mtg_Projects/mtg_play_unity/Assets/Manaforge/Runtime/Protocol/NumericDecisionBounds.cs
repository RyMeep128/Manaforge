using System;
using System.Collections.Generic;
using System.Numerics;
using Newtonsoft.Json.Linq;

namespace Manaforge.Play.Protocol
{
    // Current engine-supplied constraints only; no prompts, labels, defaults or Magic rules.
    internal sealed class NumericDecisionBounds
    {
        private readonly string family;
        private readonly long? minimum,maximum;
        private readonly List<Tuple<long,long>> amounts=new List<Tuple<long,long>>();
        internal NumericDecisionBounds(JToken request)
        {
            family=(string)request["family"];
            minimum=request["minimum"].Type==JTokenType.Null?(long?)null:(long)request["minimum"];
            maximum=request["maximum"].Type==JTokenType.Null?(long?)null:(long)request["maximum"];
            foreach(var amount in request["amounts"])amounts.Add(Tuple.Create((long)amount["minimum"],(long)amount["maximum"]));
        }
        internal bool Available
        {
            get {
                if(!minimum.HasValue || !maximum.HasValue || minimum.Value>maximum.Value)return false;
                if(family=="number")return true;
                if(family!="amounts" || amounts.Count>WireMessages.MaxAmountValues)return false;
                foreach(var range in amounts)if(range.Item1>range.Item2)return false;
                return true;
            }
        }
        internal string Reject(string operation,JToken body)
        {
            if(family!=(operation=="choose_number"?"number":"amounts"))return "DECISION_FAMILY_MISMATCH";
            if(!Available)return "SESSION_NUMERIC_UNAVAILABLE";
            if(operation=="choose_number") {
                long value=(long)body["value"];
                return value<minimum.Value || value>maximum.Value?"AMOUNT_OUT_OF_RANGE":null;
            }
            var values=(JArray)body["values"];if(values.Count!=amounts.Count)return "AMOUNT_OUT_OF_RANGE";
            BigInteger total=BigInteger.Zero;
            for(int i=0;i<values.Count;i++) {
                long value=(long)values[i];var range=amounts[i];
                if(value<range.Item1 || value>range.Item2)return "AMOUNT_OUT_OF_RANGE";
                total+=value;
            }
            return total<minimum.Value || total>maximum.Value?"AMOUNT_OUT_OF_RANGE":null;
        }
    }
}
