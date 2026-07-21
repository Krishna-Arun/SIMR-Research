import { Network } from "https://esm.sh/vis-network/peer";
import { DataSet } from "https://esm.sh/vis-data/peer";
import { fetchGraphData } from "./api.js";

let network=null;
// adds the event listener to attach graph data when DOM loaded, 
document.addEventListener("DOMContentLoaded", async () => {
    try {
        const graph = await fetchGraphData();
        initGraph(graph);
    } catch (error) {
        console.warn("⚠️ No initial graph loaded. Initializing empty graph.");
        initGraph({ nodes: [], edges: [] });
    }
});


// init graph, the 
function initGraph(graph) {
    console.log(graph.nodes);
    const nodes = new DataSet(graph.nodes);
    const edges = new DataSet(graph.edges);
    console.log("Loaded edges into DataSet:", graph.edges);

    const container = document.getElementById('mynetwork');
    const data = { nodes, edges };
    const options = {
        interaction: {
            multiselect: false,
            hover: true
        }
    };

    network = new Network(container, data, options);

    network.on("select", (params) => {
        updateSidebar(params, nodes, edges);
    });

    network.on("hoverNode", (params) => {
        console.log("Hovering over node:", params.node);
    });

    network.on("hoverEdge", (params) => {
        console.log("Hovering over edge:", params.edge);
    });
}

export function updateGraphData(newNodes, newEdges) {
    if (!network) {
        console.warn('Network is not initialized yet.');
        
        return;
    }
    // cleaning up old memory in case i held onto it. 
    const oldData = network.body.data;
    const oldNodes = oldData?.nodes;
    const oldEdges = oldData?.edges;

    // Clear old datasets explicitly
    if (oldNodes && typeof oldNodes.clear === 'function') {
        oldNodes.clear();
    }
    if (oldEdges && typeof oldEdges.clear === 'function') {
        oldEdges.clear();
    }

    // actually setting the nodes. 
    network.setData({ nodes: newNodes, edges: newEdges });

    // Clear old listeners to avoid stacking
    network.off('select');
    network.off('hoverNode');
    network.off('hoverEdge');

    // Re-bind listeners
    network.on('select', (params) => {
        updateSidebar(params, newNodes, newEdges);
    });

    network.on('hoverNode', (params) => {
        console.log('Hovering over node:', params.node);
    });

    network.on('hoverEdge', (params) => {
        console.log('Hovering over edge:', params.edge);
    });

    console.log('✅ Graph data updated and listeners reattached.');
}


function updateSidebar(params, nodes, edges) {
    const infoDiv = document.getElementById('info');
    let selectedData = null;
    console.log("Loaded edges into DataSet:", edges);
    if (params.nodes.length > 0) {
        selectedData = nodes.get(params.nodes[0]);
    } else if (params.edges.length > 0) {
        selectedData = edges.get(params.edges[0]);
    }

    if (selectedData) {
        const { id, label, from, to, customData, data } = selectedData;

        let content = `<b>${label || 'Edge Selected'}</b><br>`;
        if (id !== undefined) content += `ID: ${id}<br>`;
        if (from !== undefined && to !== undefined) content += `From: ${from} → To: ${to}<br>`;

        const payloadData = customData || data;
        content += `<b>Data:</b><br>${formatCustomData(payloadData)}`;

        infoDiv.innerHTML = content;

        sendSelectionToServer({
            id,
            label,
            from,
            to,
            customData: payloadData
        });

    } else {
        infoDiv.innerHTML = 'Click a node or edge to view details here.';
    }
}

function formatCustomData(data) {
    if (!data || typeof data !== 'object') {
        return `<i>No additional data</i>`;
    }

    const entries = Object.entries(data).map(([key, value]) => {
        if (typeof value === 'object') {
            return `<div><b>${key}:</b><pre>${JSON.stringify(value, null, 2)}</pre></div>`;
        } else {
            return `<div><b>${key}:</b> ${value}</div>`;
        }
    });

    return entries.join('');
}

async function sendSelectionToServer(data) {
    try {
        const response = await fetch('/api/selection', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });

        if (!response.ok) {
            console.error('Failed to send selection to server:', response.statusText);
        }
    } catch (error) {
        console.error('Error sending selection to server:', error);
    }
}
