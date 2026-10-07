import type { AnimalArchetype } from "./types.ts";

/** Reviewed source classification UUIDs. Labels are documentation only; see docs/scientific-semantics.md. */
export type TaxonomicVisualRule = { id: string; label: string } & ({ archetype: AnimalArchetype; inherit: boolean } | { neutral: true });
export const taxonomicVisualRules: readonly TaxonomicVisualRule[] = [
  {
    "id": "417a3de6-c84d-4fb7-8d82-c95582d709f9",
    "label": "Cingulata",
    "archetype": "armadillo",
    "inherit": true
  },
  {
    "id": "0960fffc-fbae-4b4d-82eb-d954dac1e858",
    "label": "Glyptodontidae",
    "neutral": true
  },
  {
    "id": "0e66c062-8580-4b70-8ba1-76aef8b7c921",
    "label": "Lagomorpha",
    "archetype": "lagomorph",
    "inherit": true
  },
  {
    "id": "6003c972-adbb-4dc7-8a33-ab98be8bf098",
    "label": "Rodentia",
    "archetype": "rodent",
    "inherit": true
  },
  {
    "id": "9296c8d7-f634-416d-8d2e-fb8a45025b01",
    "label": "Chiroptera",
    "archetype": "bat",
    "inherit": true
  },
  {
    "id": "42943182-8578-496f-8e4c-51c75ca83af6",
    "label": "Sirenia",
    "archetype": "sirenian",
    "inherit": true
  },
  {
    "id": "6bf8673d-39f2-4d92-88e2-e67c6bd51b99",
    "label": "Protosirenidae",
    "neutral": true
  },
  {
    "id": "37687cfa-c993-4cbf-89e7-84ce746156be",
    "label": "Prorastomidae",
    "neutral": true
  },
  {
    "id": "95803e37-f9dc-4702-8ba5-469fa4b15ccb",
    "label": "Proboscidea",
    "archetype": "proboscidean",
    "inherit": true
  },
  {
    "id": "e14f5ab5-76f4-44ee-8c4b-805a94b3971a",
    "label": "Perissodactyla",
    "archetype": "terrestrial-ungulate",
    "inherit": true
  },
  {
    "id": "4998685a-6fae-48c9-858a-afe33f6fbf8c",
    "label": "Cervidae",
    "archetype": "terrestrial-ungulate",
    "inherit": true
  },
  {
    "id": "a9cc760b-bfe5-42c3-844d-4bc3bb224148",
    "label": "Bovidae",
    "archetype": "terrestrial-ungulate",
    "inherit": true
  },
  {
    "id": "dde13772-7d38-4f2c-808f-2683da52b8f0",
    "label": "Antilocapridae",
    "archetype": "terrestrial-ungulate",
    "inherit": true
  },
  {
    "id": "9ec15ebe-b0d0-402d-8018-a056e150ad92",
    "label": "Dromomerycidae",
    "archetype": "terrestrial-ungulate",
    "inherit": true
  },
  {
    "id": "203cbf0b-6463-4847-8654-7bbca3ab630a",
    "label": "Moschidae",
    "archetype": "terrestrial-ungulate",
    "inherit": true
  },
  {
    "id": "1891594b-df45-495f-855c-1174915306f0",
    "label": "Camelidae",
    "archetype": "terrestrial-ungulate",
    "inherit": true
  },
  {
    "id": "927f8d51-2728-48f5-8874-aee017d19864",
    "label": "Tayassuidae",
    "archetype": "terrestrial-ungulate",
    "inherit": true
  },
  {
    "id": "d92c05ac-93fe-43a0-8e36-7ff40a98b628",
    "label": "Chalicotheriidae",
    "neutral": true
  },
  {
    "id": "df32e392-793d-4f33-8a11-d5b57b43db63",
    "label": "Testudines",
    "archetype": "turtle",
    "inherit": true
  },
  {
    "id": "99ec1eb2-d6c0-43d5-8e62-a57df393242f",
    "label": "Colubridae",
    "archetype": "snake",
    "inherit": true
  },
  {
    "id": "77d60955-3cb5-4d41-8d53-34d611a60e54",
    "label": "Natricidae",
    "archetype": "snake",
    "inherit": true
  },
  {
    "id": "1366dd08-ad43-4209-8f5c-ee85775cb663",
    "label": "Boidae",
    "archetype": "snake",
    "inherit": true
  },
  {
    "id": "14233752-e1e0-4ca5-868e-8b0e37babf1e",
    "label": "Dipsadidae",
    "archetype": "snake",
    "inherit": true
  },
  {
    "id": "f5c1f637-9246-4dc5-8f9b-58433e0dc5ed",
    "label": "Viperidae",
    "archetype": "snake",
    "inherit": true
  },
  {
    "id": "dfcdd70e-b271-4ea6-86e6-553b77a88d36",
    "label": "Elapidae",
    "archetype": "snake",
    "inherit": true
  },
  {
    "id": "2fce8ac4-8ff7-4ff7-814d-92fcd664a1b6",
    "label": "Palaeophiidae",
    "archetype": "snake",
    "inherit": true
  },
  {
    "id": "f2ad17f2-4819-4949-8657-3f4511bd18da",
    "label": "Aniliidae",
    "archetype": "snake",
    "inherit": true
  },
  {
    "id": "551450fa-0588-493c-8e2d-863671206da0",
    "label": "Tropidophiidae",
    "archetype": "snake",
    "inherit": true
  },
  {
    "id": "e6eca45b-f3ce-464c-8343-db258136619c",
    "label": "Serpentes",
    "archetype": "snake",
    "inherit": false
  },
  {
    "id": "39331e8c-a5b2-41b2-85ab-8aead9634aa4",
    "label": "Colubroidea",
    "archetype": "snake",
    "inherit": false
  },
  {
    "id": "b2807644-5ac2-4191-885b-8529f0655763",
    "label": "Scolecophidia",
    "archetype": "snake",
    "inherit": false
  },
  {
    "id": "7446b9c1-9e06-4143-85c1-3add186115b6",
    "label": "Crocodylia",
    "archetype": "crocodilian",
    "inherit": true
  },
  {
    "id": "3f5a6957-da0b-4237-805c-28cf1aec37eb",
    "label": "Osteichthyes",
    "archetype": "bony-fish",
    "inherit": true
  },
  {
    "id": "c023aa87-f765-4322-8b04-f4424fd75e07",
    "label": "Anguilliformes",
    "neutral": true
  },
  {
    "id": "a8f07f30-7cf0-42ce-898a-3d1cff7f626a",
    "label": "Pleuronectiformes",
    "neutral": true
  },
  {
    "id": "f91a8871-235f-4022-83a2-4a49af1badd7",
    "label": "Syngnathidae",
    "neutral": true
  },
  {
    "id": "136b36cb-e2c3-4703-8583-cfb53c5e75f3",
    "label": "Aves",
    "archetype": "bird",
    "inherit": true
  },
  {
    "id": "67c74766-cca4-4651-85b9-4f540eb96ff1",
    "label": "Anura",
    "archetype": "frog",
    "inherit": true
  },
  {
    "id": "724fc6fb-b770-4483-83c6-b2745e61539a",
    "label": "Carcharhiniformes",
    "archetype": "shark",
    "inherit": true
  },
  {
    "id": "72cc7521-df3c-4183-8902-b30c8f72442c",
    "label": "Lamniformes",
    "archetype": "shark",
    "inherit": true
  },
  {
    "id": "e01ab4d2-a7c6-458b-8a04-99efe1b17756",
    "label": "Squaliformes",
    "archetype": "shark",
    "inherit": true
  },
  {
    "id": "27b8891f-26e7-43c6-8c13-35de5fdac41c",
    "label": "Orectolobiformes",
    "archetype": "shark",
    "inherit": true
  },
  {
    "id": "8d6f4d80-c89a-4efb-89d0-e1fd7dcc09fb",
    "label": "Hexanchiformes",
    "archetype": "shark",
    "inherit": true
  },
  {
    "id": "ce9697c2-f701-4d41-879a-2e08f19fdf90",
    "label": "Heterodontiformes",
    "archetype": "shark",
    "inherit": true
  },
  {
    "id": "c9e31fbc-86bb-445b-8c56-42095f58e449",
    "label": "Artiodactyla",
    "neutral": true
  },
  {
    "id": "ac4d3dff-af24-46dc-8aff-6423bb3a2b7a",
    "label": "Ferae",
    "neutral": true
  },
  {
    "id": "88e0b761-77e8-4938-8222-aa714307c941",
    "label": "Pilosa",
    "neutral": true
  },
  {
    "id": "f40a40e7-0a9c-4f4d-8757-f0fc2cb0c5dd",
    "label": "Eulipotyphla",
    "neutral": true
  },
  {
    "id": "659077d7-a8db-4152-8898-2c2de9d2b6ef",
    "label": "Desmostylia",
    "neutral": true
  },
  {
    "id": "956bf44a-61bd-43f7-89d5-185fd33333f1",
    "label": "Apatotheria",
    "neutral": true
  },
  {
    "id": "5fa0ef36-ee22-4759-8e0f-cb487a7fe246",
    "label": "Reptilia",
    "neutral": true
  },
  {
    "id": "421cb554-9eb9-4f0a-8add-217d50a2f072",
    "label": "Squamata",
    "neutral": true
  },
  {
    "id": "73b75da2-7e6f-4809-8362-64bd088a28d0",
    "label": "Amphibia",
    "neutral": true
  },
  {
    "id": "7e074c62-d29f-4cb0-84d5-9167be54aec4",
    "label": "Urodela",
    "neutral": true
  },
  {
    "id": "dc7ac19f-a869-4e25-852b-88ed89c6bcb1",
    "label": "Chondrichthyes",
    "neutral": true
  },
  {
    "id": "92f86a10-48d7-4591-836a-037eaf8abfb1",
    "label": "Rhinopristiformes",
    "neutral": true
  },
  {
    "id": "bf7c1a50-318d-48a9-8526-aff74be29765",
    "label": "Squatiniformes",
    "neutral": true
  }
];
export const mammaliaId = "97811091-a18d-4904-8016-dfb790dd43cd";
